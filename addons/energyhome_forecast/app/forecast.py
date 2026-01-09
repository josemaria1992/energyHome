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


def build_forecast(
    df: pd.DataFrame,
    horizon_hours: int,
    ilc_curve: Dict[str, Dict[int, float]],
) -> Tuple[List[str], Dict[str, List[float]]]:
    if df.empty:
        latest_local = datetime.now()
    else:
        latest_local = df["ts_local"].max()
    start = latest_local + timedelta(minutes=15)
    steps = int(horizon_hours * 4)
    timestamps = [start + timedelta(minutes=15 * i) for i in range(steps)]

    outputs: Dict[str, List[float]] = {}
    for signal in ["total_w", "l1_w", "l2_w", "l3_w"]:
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
