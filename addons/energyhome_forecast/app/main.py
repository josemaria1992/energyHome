from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from zoneinfo import ZoneInfo

import forecast as forecast_module
from ha_client import HAClient
from ilc import should_update_ilc, update_ilc_curve, update_ilc_curve_from_forecast
from models import AppConfig, load_config
from storage import (
    daily_forecast_exists,
    fetch_avg_for_multiple_entities,
    fetch_binned_between,
    fetch_binned_since,
    fetch_ilc_curve,
    fetch_latest_measurements,
    fetch_points_count,
    get_metadata,
    init_db,
    insert_measurements,
    load_daily_forecast,
    load_daily_forecast_metrics,
    save_daily_forecast,
    save_daily_forecast_metrics,
    save_ilc_curve,
    set_metadata,
    upsert_binned,
)
from ui import render_dashboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("energyhome")

app = FastAPI()
config: AppConfig = load_config()
ha_client: HAClient | None = None

def _now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def _local_tz() -> ZoneInfo:
    return ZoneInfo(config.timezone)


def _local_bin_start(ts_utc: datetime) -> datetime:
    local_ts = ts_utc.astimezone(_local_tz())
    minute = (local_ts.minute // config.bin_minutes) * config.bin_minutes
    return local_ts.replace(minute=minute, second=0, microsecond=0)


def _dataframe_from_rows(rows: List[Dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts_local", "total_w", "l1_w", "l2_w", "l3_w", "grid_l1_w", "grid_l2_w", "grid_l3_w", "inverter_w"])
    df = pd.DataFrame(rows)
    df["ts_local"] = pd.to_datetime(df["ts_local_bin_start"], utc=False)
    return df


async def poll_once() -> None:
    ts_utc = _now_utc()
    entities = config.entities
    entity_map = {
        "total_w": entities.total_load_power,
        "l1_w": entities.l1_load_power,
        "l2_w": entities.l2_load_power,
        "l3_w": entities.l3_load_power,
        "inverter_w": entities.inverter_load_power,
    }
    optional_entities = {
        "soc": entities.soc,
        "grid_l1_current": entities.grid_l1_current,
        "grid_l2_current": entities.grid_l2_current,
        "grid_l3_current": entities.grid_l3_current,
        "grid_l1_power": entities.grid_l1_power,
        "grid_l2_power": entities.grid_l2_power,
        "grid_l3_power": entities.grid_l3_power,
    }

    results: Dict[str, float | None] = {}
    if ha_client is None:
        logger.error("HA client not initialized")
        return
    for key, entity_id in {**entity_map, **optional_entities}.items():
        if not entity_id:
            results[key] = None
            continue
        try:
            value = await ha_client.fetch_entity_state(entity_id)
            results[key] = value
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch %s: %s", entity_id, exc)
            results[key] = None

    measurements = []
    for key, entity_id in {**entity_map, **optional_entities}.items():
        if not entity_id:
            continue
        measurements.append((ts_utc.isoformat(), entity_id, results.get(key)))
    insert_measurements(config.db_path, measurements)

    # Compute 15-minute bin averages
    bin_start_local = _local_bin_start(ts_utc)
    bin_end_local = bin_start_local + timedelta(minutes=config.bin_minutes)
    bin_start_utc = bin_start_local.astimezone(ZoneInfo("UTC"))
    bin_end_utc = bin_end_local.astimezone(ZoneInfo("UTC"))

    # Fetch averages for all entities in the bin
    entity_ids = [e for e in {**entity_map, **optional_entities}.values() if e]
    averages = fetch_avg_for_multiple_entities(
        config.db_path, entity_ids, bin_start_utc.isoformat(), bin_end_utc.isoformat()
    )

    # Extract averaged values
    avg_total_w = averages.get(entities.total_load_power)
    avg_l1_w = averages.get(entities.l1_load_power)
    avg_l2_w = averages.get(entities.l2_load_power)
    avg_l3_w = averages.get(entities.l3_load_power)
    avg_inverter_w = averages.get(entities.inverter_load_power)

    # Compute grid power: average current * voltage, or use power sensor if available
    avg_grid_l1_current = averages.get(entities.grid_l1_current)
    avg_grid_l2_current = averages.get(entities.grid_l2_current)
    avg_grid_l3_current = averages.get(entities.grid_l3_current)
    avg_grid_l1_w = averages.get(entities.grid_l1_power)
    avg_grid_l2_w = averages.get(entities.grid_l2_power)
    avg_grid_l3_w = averages.get(entities.grid_l3_power)

    # Fall back to current-derived estimate if power sensor is missing
    if avg_grid_l1_w is None and avg_grid_l1_current is not None:
        avg_grid_l1_w = avg_grid_l1_current * config.grid_voltage_v
    if avg_grid_l2_w is None and avg_grid_l2_current is not None:
        avg_grid_l2_w = avg_grid_l2_current * config.grid_voltage_v
    if avg_grid_l3_w is None and avg_grid_l3_current is not None:
        avg_grid_l3_w = avg_grid_l3_current * config.grid_voltage_v

    # Store averaged values into binned table
    upsert_binned(
        config.db_path,
        bin_start_local.isoformat(),
        avg_total_w,
        avg_l1_w,
        avg_l2_w,
        avg_l3_w,
        avg_grid_l1_w,
        avg_grid_l2_w,
        avg_grid_l3_w,
        avg_inverter_w,
    )

    set_metadata(config.db_path, "last_poll_utc", ts_utc.isoformat())

    # Check for daily rollover
    await check_daily_rollover(bin_start_local)

    # Log poll completion summary
    next_poll = _now_utc() + timedelta(seconds=config.poll_interval_seconds)
    logger.info(
        "Poll complete: inserted=%d measurements, bin=%s, next_poll_in=%d sec (at %s UTC)",
        len(measurements),
        bin_start.isoformat(),
        config.poll_interval_seconds,
        next_poll.strftime("%H:%M:%S"),
    )


async def poll_loop() -> None:
    first_poll = True
    while True:
        try:
            await poll_once()
            if first_poll:
                first_poll = False
        except Exception as exc:  # noqa: BLE001
            logger.exception("Polling failed: %s", exc)
        next_poll = _now_utc() + timedelta(seconds=config.poll_interval_seconds)
        logger.info("Next poll scheduled in %d seconds (at %s UTC)", config.poll_interval_seconds, next_poll.strftime("%H:%M:%S"))
        await asyncio.sleep(config.poll_interval_seconds)


async def check_daily_rollover(now_local: datetime) -> None:
    """
    Check if we've crossed midnight since last rollover.
    If yes: train on yesterday's data, generate tomorrow's forecast.
    """
    today = now_local.date()
    last_rollover_date_str = get_metadata(config.db_path, "last_rollover_date")

    # Check if we've already done rollover for today
    if last_rollover_date_str == today.isoformat():
        return

    logger.info("Daily rollover detected: today=%s, last_rollover=%s", today, last_rollover_date_str)

    yesterday = today - timedelta(days=1)

    # Step 1: Train ILC on yesterday's data (if learning_mode is ilc_yesterday)
    if config.learning_mode == "ilc_yesterday":
        if daily_forecast_exists(config.db_path, yesterday.isoformat()):
            logger.info("Training ILC on yesterday's data (%s)", yesterday)
            await train_ilc_on_yesterday(yesterday)
        else:
            logger.warning("Cannot train ILC: no forecast exists for yesterday (%s)", yesterday)

    # Step 2: Generate and store tomorrow's forecast
    tomorrow = today + timedelta(days=1)
    logger.info("Generating forecast for tomorrow (%s)", tomorrow)
    await generate_and_store_forecast(tomorrow)

    # Step 3: Bootstrap today's forecast if missing (first-time run)
    if not daily_forecast_exists(config.db_path, today.isoformat()):
        logger.info("Bootstrap: generating forecast for today (%s)", today)
        await generate_and_store_forecast(today)

    # Mark rollover complete
    set_metadata(config.db_path, "last_rollover_date", today.isoformat())
    logger.info("Daily rollover complete")


async def train_ilc_on_yesterday(yesterday: datetime.date) -> None:
    """Train ILC using yesterday's frozen forecast vs actual data."""
    # Load yesterday's frozen forecast
    forecast_dict = load_daily_forecast(config.db_path, yesterday.isoformat())
    if not forecast_dict:
        logger.warning("No frozen forecast found for %s", yesterday)
        return

    # Load yesterday's actual data
    start_local = datetime.combine(yesterday, datetime.min.time(), tzinfo=_local_tz())
    end_local = datetime.combine(yesterday + timedelta(days=1), datetime.min.time(), tzinfo=_local_tz())
    rows = fetch_binned_between(config.db_path, start_local.isoformat(), end_local.isoformat())
    actual_dict = {}
    for row in rows:
        ts_local = datetime.fromisoformat(row["ts_local_bin_start"])
        bin_idx = int(ts_local.hour * 4 + ts_local.minute / 15)
        for signal in ["total_w", "l1_w", "l2_w", "l3_w", "inverter_w"]:
            if signal not in actual_dict:
                actual_dict[signal] = {}
            value = row.get(signal)
            if value is not None:
                actual_dict[signal][bin_idx] = float(value)

    # Update ILC curves
    for signal, cmax in {
        "total_w": 4000.0,
        "l1_w": 2000.0,
        "l2_w": 2000.0,
        "l3_w": 2000.0,
        "inverter_w": 4000.0,
    }.items():
        existing_curve = fetch_ilc_curve(config.db_path, signal)
        forecast_by_bin = forecast_dict.get(signal, {})
        actual_by_bin = actual_dict.get(signal, {})

        if not forecast_by_bin or not actual_by_bin:
            logger.warning("Skipping ILC update for %s: missing data", signal)
            continue

        updated_curve = update_ilc_curve_from_forecast(
            existing_curve, forecast_by_bin, actual_by_bin, alpha=0.2, cmax=cmax
        )
        save_ilc_curve(config.db_path, signal, updated_curve)
        logger.info("Updated ILC curve for %s", signal)

    # Optionally compute and save metrics for yesterday
    await compute_and_save_metrics(yesterday, forecast_dict, actual_dict)


async def compute_and_save_metrics(
    date_local: datetime.date,
    forecast_dict: Dict[str, Dict[int, float]],
    actual_dict: Dict[str, Dict[int, float]],
) -> None:
    """Compute and save accuracy metrics for a completed day."""
    signal = "total_w"  # Focus on total load for metrics
    forecast_by_bin = forecast_dict.get(signal, {})
    actual_by_bin = actual_dict.get(signal, {})

    if not forecast_by_bin or not actual_by_bin:
        logger.warning("Cannot compute metrics for %s: missing data", date_local)
        return

    # Compute MAE, MAPE, accuracy
    errors = []
    pct_errors = []
    for bin_idx in range(96):
        if bin_idx in forecast_by_bin and bin_idx in actual_by_bin:
            forecast_val = forecast_by_bin[bin_idx]
            actual_val = actual_by_bin[bin_idx]
            error = abs(actual_val - forecast_val)
            errors.append(error)
            if actual_val > 0:
                pct_errors.append(100.0 * error / actual_val)

    if not errors:
        logger.warning("No valid bins to compute metrics for %s", date_local)
        return

    mae = float(np.mean(errors))
    mape = float(np.mean(pct_errors)) if pct_errors else 0.0

    # Compute accuracy as NMAE-based
    mean_actual = float(np.mean([actual_by_bin[i] for i in actual_by_bin if i < 96]))
    nmae = mae / (mean_actual + 1e-6)
    accuracy_pct = max(0.0, 100.0 * (1.0 - nmae))

    save_daily_forecast_metrics(
        config.db_path,
        date_local.isoformat(),
        signal,
        mae,
        mape,
        accuracy_pct,
        len(errors),
        datetime.now(tz=_local_tz()).isoformat(),
    )
    logger.info(
        "Saved metrics for %s: MAE=%.1fW, MAPE=%.1f%%, Accuracy=%.1f%%",
        date_local, mae, mape, accuracy_pct
    )


async def generate_and_store_forecast(target_date: datetime.date) -> None:
    """Generate and store a frozen forecast for a specific date."""
    # Fetch historical data (exclude target date)
    start_local = (datetime.now(tz=_local_tz()) - timedelta(days=14)).isoformat()
    rows = fetch_binned_since(config.db_path, start_local)
    df = _dataframe_from_rows(rows)

    # Load ILC curves
    ilc_curves = {
        "total_w": fetch_ilc_curve(config.db_path, "total_w"),
        "l1_w": fetch_ilc_curve(config.db_path, "l1_w"),
        "l2_w": fetch_ilc_curve(config.db_path, "l2_w"),
        "l3_w": fetch_ilc_curve(config.db_path, "l3_w"),
        "inverter_w": fetch_ilc_curve(config.db_path, "inverter_w"),
    }

    # Build forecast for target date
    timestamps, forecast_dict = forecast_module.build_day_forecast(
        df, target_date, _local_tz(), ilc_curves, config.learning_mode
    )

    # Save to database
    created_local = datetime.now(tz=_local_tz()).isoformat()
    save_daily_forecast(config.db_path, target_date.isoformat(), created_local, forecast_dict)
    logger.info("Saved frozen forecast for %s (96 bins)", target_date)


def build_history(hours: int) -> Dict[str, List]:
    now_local = _now_utc().astimezone(_local_tz())
    start_local = (now_local - timedelta(hours=hours)).isoformat()
    rows = fetch_binned_since(config.db_path, start_local)
    df = _dataframe_from_rows(rows)
    return {
        "timestamps": df["ts_local"].dt.strftime("%Y-%m-%dT%H:%M:%S%z").tolist(),
        "total_w": df.get("total_w", pd.Series(dtype=float)).tolist(),
        "l1_w": df.get("l1_w", pd.Series(dtype=float)).tolist(),
        "l2_w": df.get("l2_w", pd.Series(dtype=float)).tolist(),
        "l3_w": df.get("l3_w", pd.Series(dtype=float)).tolist(),
        "grid_l1_w": df.get("grid_l1_w", pd.Series(dtype=float)).tolist(),
        "grid_l2_w": df.get("grid_l2_w", pd.Series(dtype=float)).tolist(),
        "grid_l3_w": df.get("grid_l3_w", pd.Series(dtype=float)).tolist(),
        "inverter_w": df.get("inverter_w", pd.Series(dtype=float)).tolist(),
    }


def build_forecast_payload() -> Dict[str, List]:
    now_local = _now_utc().astimezone(_local_tz())
    start_local = (now_local - timedelta(days=14)).isoformat()
    rows = fetch_binned_since(config.db_path, start_local)
    df = _dataframe_from_rows(rows)
    curves = {
        "total_w": fetch_ilc_curve(config.db_path, "total_w"),
        "l1_w": fetch_ilc_curve(config.db_path, "l1_w"),
        "l2_w": fetch_ilc_curve(config.db_path, "l2_w"),
        "l3_w": fetch_ilc_curve(config.db_path, "l3_w"),
        "inverter_w": fetch_ilc_curve(config.db_path, "inverter_w"),
    }
    timestamps, values = forecast_module.build_forecast(
        df, config.horizon_hours, curves, config.learning_mode
    )
    return {"timestamps": timestamps, **values}


@app.on_event("startup")
async def startup_event() -> None:
    global ha_client
    logger.info("EnergyHome Forecast v0.4.2 starting...")
    logger.info("Database path: %s", config.db_path)
    logger.info("Polling interval: %d seconds (bin size: %d minutes)", config.poll_interval_seconds, config.bin_minutes)
    logger.info("Learning mode: %s", config.learning_mode)
    logger.info("Timezone: %s", config.timezone)
    logger.info("Forecast horizon: %d hours", config.horizon_hours)
    init_db(config.db_path)
    ha_client = HAClient(config.ha_url, config.ha_token)
    # Validate auth before starting poll loop to prevent endless log spam
    await ha_client.validate_auth()
    asyncio.create_task(poll_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if ha_client is not None:
        await ha_client.close()
        
@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="ui")
    
@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> Dict[str, object]:
    return {
        "last_poll_utc": get_metadata(config.db_path, "last_poll_utc"),
        "db_path": config.db_path,
        "configured_entities": config.entities.__dict__,
        "points_stored": fetch_points_count(config.db_path),
        "last_ilc_update_local": get_metadata(config.db_path, "last_ilc_update_local"),
    }


@app.get("/api/history")
async def history(hours: int = 72) -> Dict[str, List]:
    return build_history(hours)


@app.get("/api/forecast")
async def forecast(date: str | None = None) -> Dict[str, List]:
    """
    Get frozen forecast for a specific date (default: today).
    Returns timestamps and values for exactly 96 bins (one full day).
    """
    if date:
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            return JSONResponse(
                content={"error": f"Invalid date format: {date}. Use YYYY-MM-DD."},
                status_code=400
            )
    else:
        target_date = _now_utc().astimezone(_local_tz()).date()

    # Load frozen forecast from storage
    forecast_dict = load_daily_forecast(config.db_path, target_date.isoformat())

    if not forecast_dict:
        # Bootstrap: generate forecast if missing
        logger.warning("No frozen forecast found for %s, generating on-demand", target_date)
        await generate_and_store_forecast(target_date)
        forecast_dict = load_daily_forecast(config.db_path, target_date.isoformat())

    # Convert to timestamp + values format
    start_of_day = datetime.combine(target_date, datetime.min.time(), tzinfo=_local_tz())
    timestamps = [start_of_day + timedelta(minutes=15 * i) for i in range(96)]

    result = {
        "timestamps": [ts.isoformat() for ts in timestamps],
        "total_w": [forecast_dict.get("total_w", {}).get(i, 0.0) for i in range(96)],
        "l1_w": [forecast_dict.get("l1_w", {}).get(i, 0.0) for i in range(96)],
        "l2_w": [forecast_dict.get("l2_w", {}).get(i, 0.0) for i in range(96)],
        "l3_w": [forecast_dict.get("l3_w", {}).get(i, 0.0) for i in range(96)],
        "inverter_w": [forecast_dict.get("inverter_w", {}).get(i, 0.0) for i in range(96)],
    }
    return result


@app.get("/api/forecast/live")
async def forecast_live() -> Dict[str, List]:
    """
    Get live rolling 48h forecast (old behavior).
    This recomputes the forecast from current data and is useful for debugging.
    """
    return build_forecast_payload()


@app.get("/api/latest")
async def latest():
    """Get the latest raw measurements from the most recent poll."""
    try:
        raw = fetch_latest_measurements(config.db_path)
        ts_utc = raw.get("ts_utc")
        values = raw.get("values", {})
    except Exception as exc:
        logger.exception("fetch_latest_measurements failed")
        return JSONResponse(
            content={
                "ts_utc": None,
                "signals": {},
                "error": str(exc)
            },
            media_type="application/json"
        )

    entities = config.entities
    signals = {}

    def get_val(entity_id):
        if entity_id and entity_id in values:
            v = values[entity_id]
            try:
                return float(v)
            except Exception:
                return None
        return None

    signals["total_w"] = get_val(entities.total_load_power)
    signals["l1_w"] = get_val(entities.l1_load_power)
    signals["l2_w"] = get_val(entities.l2_load_power)
    signals["l3_w"] = get_val(entities.l3_load_power)

    signals["grid_l1_a"] = get_val(entities.grid_l1_current)
    signals["grid_l2_a"] = get_val(entities.grid_l2_current)
    signals["grid_l3_a"] = get_val(entities.grid_l3_current)

    grid_l1_w = get_val(entities.grid_l1_power)
    grid_l2_w = get_val(entities.grid_l2_power)
    grid_l3_w = get_val(entities.grid_l3_power)

    if grid_l1_w is None and signals["grid_l1_a"] is not None:
        grid_l1_w = signals["grid_l1_a"] * config.grid_voltage_v
        signals["grid_l1_w_estimated"] = True
    else:
        signals["grid_l1_w_estimated"] = False

    if grid_l2_w is None and signals["grid_l2_a"] is not None:
        grid_l2_w = signals["grid_l2_a"] * config.grid_voltage_v
        signals["grid_l2_w_estimated"] = True
    else:
        signals["grid_l2_w_estimated"] = False

    if grid_l3_w is None and signals["grid_l3_a"] is not None:
        grid_l3_w = signals["grid_l3_a"] * config.grid_voltage_v
        signals["grid_l3_w_estimated"] = True
    else:
        signals["grid_l3_w_estimated"] = False

    signals["grid_l1_w"] = grid_l1_w
    signals["grid_l2_w"] = grid_l2_w
    signals["grid_l3_w"] = grid_l3_w

    signals["inverter_w"] = get_val(entities.inverter_load_power)
    signals["soc_pct"] = get_val(entities.soc)

    return JSONResponse(
        content={
            "ts_utc": ts_utc,
            "signals": signals
        },
        media_type="application/json"
    )


@app.post("/api/recompute")
async def recompute() -> Dict[str, str]:
    _ = build_forecast_payload()
    return {"status": "ok"}


@app.post("/api/ilc/update")
async def ilc_update() -> Dict[str, str]:
    if config.learning_mode != "ilc_yesterday":
        return {
            "status": "skipped",
            "reason": f"learning_mode={config.learning_mode}; ILC disabled"
        }
    now_local = _now_utc().astimezone(_local_tz())
    await maybe_update_ilc(now_local)
    return {"status": "ok"}


@app.post("/api/poll_now")
async def poll_now() -> Dict[str, str]:
    """Trigger an immediate poll for testing/development."""
    logger.info("Manual poll triggered via /api/poll_now")
    try:
        await poll_once()
        return {"status": "ok", "message": "Poll completed successfully"}
    except Exception as exc:
        logger.exception("Manual poll failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/api/export_db")
async def export_db():
    """Export/download the database file for backup purposes."""
    import os
    if not os.path.exists(config.db_path):
        return JSONResponse(
            content={"error": "Database file not found"},
            status_code=404
        )

    logger.info("Database export requested")
    return FileResponse(
        path=config.db_path,
        media_type="application/x-sqlite3",
        filename="energyhome_backup.sqlite"
    )


@app.get("/api/metrics")
async def metrics() -> Dict[str, object]:
    """
    Compute forecast accuracy metrics by comparing model estimates with actual values.
    This is a "hindcast" accuracy - comparing current model predictions to historical data.
    """
    evaluation_days = 7
    now_local = _now_utc().astimezone(_local_tz())
    start_local = (now_local - timedelta(days=evaluation_days)).isoformat()

    # Fetch historical binned data
    rows = fetch_binned_since(config.db_path, start_local)
    df = _dataframe_from_rows(rows)

    if df.empty:
        return {
            "evaluation_window_days": evaluation_days,
            "accuracy_total_w_pct": None,
            "n_points_used": 0,
            "learning_mode": config.learning_mode,
            "timestamp": now_local.isoformat(),
            "error": "No historical data available"
        }

    # Build baseline models based on learning mode
    if config.learning_mode == "weekday_profile":
        # Build weekday-specific baselines
        weekday_baselines = {}
        for dow in range(7):
            baseline = forecast_module.compute_baseline_weekday(df, "total_w", dow)
            weekday_baselines[dow] = forecast_module.smooth_baseline(baseline)

        # Compute estimates for each historical point
        estimates = []
        actuals = []
        for _, row in df.iterrows():
            actual = row.get("total_w")
            if actual is None or pd.isna(actual):
                continue
            ts = row["ts_local"]
            dow = ts.dayofweek
            bin_idx = int(ts.hour * 4 + ts.minute / 15)
            estimate = weekday_baselines[dow].get(bin_idx, 0.0)
            estimates.append(max(0.0, estimate))
            actuals.append(actual)

    elif config.learning_mode == "off":
        # Global baseline without ILC
        baseline = forecast_module.compute_baseline(df, "total_w")
        baseline = forecast_module.smooth_baseline(baseline)

        estimates = []
        actuals = []
        for _, row in df.iterrows():
            actual = row.get("total_w")
            if actual is None or pd.isna(actual):
                continue
            ts = row["ts_local"]
            bin_idx = int(ts.hour * 4 + ts.minute / 15)
            estimate = baseline.get(bin_idx, 0.0)
            estimates.append(max(0.0, estimate))
            actuals.append(actual)

    else:  # learning_mode == "ilc_yesterday"
        # Global baseline + ILC correction
        baseline = forecast_module.compute_baseline(df, "total_w")
        baseline = forecast_module.smooth_baseline(baseline)
        ilc_curve = fetch_ilc_curve(config.db_path, "total_w")

        estimates = []
        actuals = []
        for _, row in df.iterrows():
            actual = row.get("total_w")
            if actual is None or pd.isna(actual):
                continue
            ts = row["ts_local"]
            bin_idx = int(ts.hour * 4 + ts.minute / 15)
            base_value = baseline.get(bin_idx, 0.0)
            correction = ilc_curve.get(bin_idx, 0.0)
            estimate = base_value + correction
            estimates.append(max(0.0, estimate))
            actuals.append(actual)

    # Compute accuracy metrics
    n_points = len(actuals)
    if n_points == 0:
        return {
            "evaluation_window_days": evaluation_days,
            "accuracy_total_w_pct": None,
            "n_points_used": 0,
            "learning_mode": config.learning_mode,
            "timestamp": now_local.isoformat(),
            "error": "No valid data points for evaluation"
        }

    # Calculate NMAE (Normalized Mean Absolute Error)
    actuals_arr = np.array(actuals)
    estimates_arr = np.array(estimates)
    mae = np.mean(np.abs(actuals_arr - estimates_arr))
    mean_actual = np.mean(np.abs(actuals_arr)) + 1e-6  # epsilon to prevent division by zero
    nmae = mae / mean_actual
    accuracy_pct = max(0.0, 100.0 * (1.0 - nmae))

    return {
        "evaluation_window_days": evaluation_days,
        "accuracy_total_w_pct": round(accuracy_pct, 1),
        "n_points_used": n_points,
        "learning_mode": config.learning_mode,
        "timestamp": now_local.isoformat(),
    }


@app.get("/api/metrics/daily")
async def metrics_daily(date: str | None = None) -> Dict[str, object]:
    """
    Get day-ahead forecast accuracy metrics for a completed day.
    Default: most recently completed day (yesterday).
    """
    now_local = _now_utc().astimezone(_local_tz())

    if date:
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            return JSONResponse(
                content={"error": f"Invalid date format: {date}. Use YYYY-MM-DD."},
                status_code=400
            )
    else:
        # Default to yesterday (most recently completed day)
        target_date = (now_local - timedelta(days=1)).date()

    # Load stored metrics
    metrics = load_daily_forecast_metrics(config.db_path, target_date.isoformat())

    if metrics:
        return {
            "date_evaluated": target_date.isoformat(),
            "signal": metrics["signal"],
            "mae": round(metrics["mae"], 1),
            "mape": round(metrics["mape"], 1),
            "accuracy_pct": round(metrics["accuracy_pct"], 1),
            "n_bins_compared": metrics["n_bins_compared"],
            "created_local": metrics["created_local"],
        }
    else:
        return {
            "date_evaluated": target_date.isoformat(),
            "error": f"No metrics available for {target_date}",
            "signal": None,
            "mae": None,
            "mape": None,
            "accuracy_pct": None,
            "n_bins_compared": 0,
        }


@app.get("/ui", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    status_payload = await status()
    history_payload = build_history(hours=72)
    forecast_payload = build_forecast_payload()
    html = render_dashboard(history_payload, forecast_payload, status_payload)
    return HTMLResponse(content=html)
