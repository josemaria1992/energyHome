from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def _bin_index(timestamp: pd.Timestamp) -> int:
    return int(timestamp.hour * 4 + timestamp.minute / 15)


def compute_baseline(df: pd.DataFrame, value_col: str, days: int = 14) -> Dict[int, float]:
    if df.empty:
        return {i: 0.0 for i in range(96)}
    df = df.copy()
    df["bin"] = df["ts_local"].apply(_bin_index)
    df["date"] = df["ts_local"].dt.date
    recent_dates = sorted(df["date"].unique())[-days:]
    df = df[df["date"].isin(recent_dates)]
    baseline = df.groupby("bin")[value_col].mean().to_dict()
    return {i: float(baseline.get(i, 0.0)) for i in range(96)}


def smooth_baseline(baseline: Dict[int, float]) -> Dict[int, float]:
    values = np.array([baseline.get(i, 0.0) for i in range(96)], dtype=float)
    kernel = np.ones(3) / 3.0
    smoothed = np.convolve(values, kernel, mode="same")
    return {i: float(smoothed[i]) for i in range(96)}


def compute_baseline_weekday(
    df: pd.DataFrame, value_col: str, dow: int, days: int = 28
) -> Dict[int, float]:
    """
    Compute baseline for a specific day of week (Monday=0 ... Sunday=6).

    Args:
        df: DataFrame with ts_local and value columns
        value_col: Name of the value column to compute baseline for
        dow: Day of week (0=Monday, 6=Sunday)
        days: Number of days to look back (default 28 for 4 weeks)

    Returns:
        Dict mapping bin index (0-95) to mean value for that time-of-day
    """
    if df.empty:
        return {i: 0.0 for i in range(96)}

    df = df.copy()
    df["bin"] = df["ts_local"].apply(_bin_index)
    df["date"] = df["ts_local"].dt.date
    df["dow"] = df["ts_local"].dt.dayofweek

    # Filter to last N days
    recent_dates = sorted(df["date"].unique())[-days:]
    df = df[df["date"].isin(recent_dates)]

    # Filter to specific day of week
    df_dow = df[df["dow"] == dow]

    if df_dow.empty:
        # Fallback: if no data for this dow, return zeros
        return {i: 0.0 for i in range(96)}

    # Compute mean per bin for this day of week
    baseline = df_dow.groupby("bin")[value_col].mean().to_dict()
    return {i: float(baseline.get(i, 0.0)) for i in range(96)}


def build_forecast(
    df: pd.DataFrame,
    horizon_hours: int,
    ilc_curve: Dict[str, Dict[int, float]],
    learning_mode: str = "ilc_yesterday",
) -> Tuple[List[str], Dict[str, List[float]]]:
    if df.empty:
        latest_local = datetime.now()
    else:
        latest_local = df["ts_local"].max()
    start = latest_local + timedelta(minutes=15)
    steps = int(horizon_hours * 4)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(steps)]

    outputs: Dict[str, List[float]] = {}
    for signal in ["total_w", "l1_w", "l2_w", "l3_w", "inverter_w"]:
        if learning_mode == "weekday_profile":
            # Build weekday-specific baselines (7 baselines, one per day)
            weekday_baselines = {}
            for dow in range(7):
                baseline = compute_baseline_weekday(df, signal, dow)
                weekday_baselines[dow] = smooth_baseline(baseline)

            # Generate forecast using appropriate weekday baseline
            values = []
            for ts in timestamps:
                dow = ts.weekday()
                bin_index = _bin_index(pd.Timestamp(ts))
                base_value = weekday_baselines[dow].get(bin_index, 0.0)
                # No ILC correction in weekday_profile mode
                values.append(float(max(0.0, base_value)))
            outputs[signal] = values

        elif learning_mode == "off":
            # Use global baseline without ILC correction
            baseline = compute_baseline(df, signal)
            baseline = smooth_baseline(baseline)
            values = []
            for ts in timestamps:
                bin_index = _bin_index(pd.Timestamp(ts))
                base_value = baseline.get(bin_index, 0.0)
                values.append(float(max(0.0, base_value)))
            outputs[signal] = values

        else:  # learning_mode == "ilc_yesterday" (default)
            # Existing behavior: global baseline + ILC correction
            baseline = compute_baseline(df, signal)
            baseline = smooth_baseline(baseline)
            curve = ilc_curve.get(signal, {})
            values = []
            for ts in timestamps:
                bin_index = _bin_index(pd.Timestamp(ts))
                base_value = baseline.get(bin_index, 0.0)
                correction = curve.get(bin_index, 0.0)
                values.append(float(max(0.0, base_value + correction)))
            outputs[signal] = values

    return [ts.isoformat() for ts in timestamps], outputs
