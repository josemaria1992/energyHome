from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from zoneinfo import ZoneInfo

import forecast as forecast_module
from ha_client import HAClient
from ilc import should_update_ilc, update_ilc_curve
from models import AppConfig, load_config
from storage import (
    fetch_binned_between,
    fetch_binned_since,
    fetch_ilc_curve,
    fetch_latest_measurements,
    fetch_points_count,
    get_metadata,
    init_db,
    insert_measurements,
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

    # Compute grid power from current if power sensors not available
    grid_l1_w = results.get("grid_l1_power")
    grid_l2_w = results.get("grid_l2_power")
    grid_l3_w = results.get("grid_l3_power")

    if grid_l1_w is None and results.get("grid_l1_current") is not None:
        grid_l1_w = results["grid_l1_current"] * config.grid_voltage_v
    if grid_l2_w is None and results.get("grid_l2_current") is not None:
        grid_l2_w = results["grid_l2_current"] * config.grid_voltage_v
    if grid_l3_w is None and results.get("grid_l3_current") is not None:
        grid_l3_w = results["grid_l3_current"] * config.grid_voltage_v

    bin_start = _local_bin_start(ts_utc)
    upsert_binned(
        config.db_path,
        bin_start.isoformat(),
        results.get("total_w"),
        results.get("l1_w"),
        results.get("l2_w"),
        results.get("l3_w"),
        grid_l1_w,
        grid_l2_w,
        grid_l3_w,
        results.get("inverter_w"),
    )

    set_metadata(config.db_path, "last_poll_utc", ts_utc.isoformat())
    await maybe_update_ilc(bin_start)

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


async def maybe_update_ilc(bin_start: datetime) -> None:
    today = bin_start.date()
    last_update = get_metadata(config.db_path, "last_ilc_update_local")
    if not should_update_ilc(last_update, today):
        return

    yesterday = today - timedelta(days=1)
    start_local = datetime.combine(yesterday, datetime.min.time(), tzinfo=_local_tz())
    end_local = datetime.combine(today, datetime.min.time(), tzinfo=_local_tz())

    rows = fetch_binned_since(config.db_path, start_local.isoformat())
    df = _dataframe_from_rows(rows)
    if df.empty:
        return

    baseline_df = df[df["ts_local"].dt.date < today]
    for signal, cmax in {
        "total_w": 4000.0,
        "l1_w": 2000.0,
        "l2_w": 2000.0,
        "l3_w": 2000.0,
        "inverter_w": 4000.0,
    }.items():
        baseline = forecast_module.compute_baseline(baseline_df, signal)
        baseline = forecast_module.smooth_baseline(baseline)
        existing_curve = fetch_ilc_curve(config.db_path, signal)
        updated_curve = update_ilc_curve(
            config.db_path,
            signal,
            baseline,
            existing_curve,
            start_local.isoformat(),
            end_local.isoformat(),
            alpha=0.2,
            cmax=cmax,
        )
        save_ilc_curve(config.db_path, signal, updated_curve)

    set_metadata(config.db_path, "last_ilc_update_local", today.isoformat())


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
    timestamps, values = forecast_module.build_forecast(df, config.horizon_hours, curves)
    return {"timestamps": timestamps, **values}


@app.on_event("startup")
async def startup_event() -> None:
    global ha_client
    logger.info("EnergyHome Forecast v0.3.0 starting...")
    logger.info("Database path: %s", config.db_path)
    logger.info("Polling interval: %d seconds (bin size: %d minutes)", config.poll_interval_seconds, config.bin_minutes)
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
async def forecast() -> Dict[str, List]:
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


@app.get("/ui", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    status_payload = await status()
    history_payload = build_history(hours=72)
    forecast_payload = build_forecast_payload()
    html = render_dashboard(history_payload, forecast_payload, status_payload)
    return HTMLResponse(content=html)
