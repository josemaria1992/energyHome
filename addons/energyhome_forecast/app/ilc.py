from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List

import numpy as np

from storage import fetch_binned_between


def smooth_curve(values: Dict[int, float]) -> Dict[int, float]:
    ordered = np.array([values.get(i, 0.0) for i in range(96)], dtype=float)
    kernel = np.ones(3) / 3.0
    smoothed = np.convolve(ordered, kernel, mode="same")
    return {i: float(smoothed[i]) for i in range(96)}


def update_ilc_curve(
    db_path: str,
    signal: str,
    baseline_by_bin: Dict[int, float],
    existing_curve: Dict[int, float],
    yesterday_start_local: str,
    today_start_local: str,
    alpha: float,
    cmax: float,
) -> Dict[int, float]:
    rows = fetch_binned_between(db_path, yesterday_start_local, today_start_local)
    values = []
    for row in rows:
        value = row.get(signal)
        if value is not None:
            values.append((row["ts_local_bin_start"], float(value)))

    curve = {i: float(existing_curve.get(i, 0.0)) for i in range(96)}
    for ts_local, actual in values:
        try:
            parsed = datetime.fromisoformat(ts_local)
        except ValueError:
            continue
        bin_index = int(parsed.hour * 4 + parsed.minute / 15)
        baseline = float(baseline_by_bin.get(bin_index, 0.0))
        error = actual - baseline
        updated = (1 - alpha) * curve[bin_index] + alpha * error
        curve[bin_index] = float(max(min(updated, cmax), -cmax))

    return smooth_curve(curve)


def should_update_ilc(last_update: str | None, today: date) -> bool:
    if not last_update:
        return True
    return last_update != today.isoformat()
