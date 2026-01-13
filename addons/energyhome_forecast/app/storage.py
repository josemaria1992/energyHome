from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                ts_utc TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                value REAL,
                PRIMARY KEY (ts_utc, entity_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS binned (
                ts_local_bin_start TEXT PRIMARY KEY,
                total_w REAL,
                l1_w REAL,
                l2_w REAL,
                l3_w REAL,
                grid_l1_w REAL,
                grid_l2_w REAL,
                grid_l3_w REAL,
                inverter_w REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ilc_curve (
                signal TEXT NOT NULL,
                bin INTEGER NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY (signal, bin)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # Daily frozen forecast table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_forecast (
                date_local TEXT NOT NULL,
                signal TEXT NOT NULL,
                bin INTEGER NOT NULL,
                value REAL NOT NULL,
                created_local TEXT NOT NULL,
                PRIMARY KEY (date_local, signal, bin)
            )
            """
        )
        # Daily forecast metrics table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_forecast_metrics (
                date_local TEXT PRIMARY KEY,
                signal TEXT NOT NULL,
                mae REAL,
                mape REAL,
                accuracy_pct REAL,
                n_bins_compared INTEGER,
                created_local TEXT NOT NULL
            )
            """
        )
        # Migration: Add new columns for existing databases
        cursor = conn.execute("PRAGMA table_info(binned)")
        columns = [row[1] for row in cursor.fetchall()]
        if "inverter_w" not in columns:
            conn.execute("ALTER TABLE binned ADD COLUMN inverter_w REAL")
        if "grid_l1_w" not in columns:
            conn.execute("ALTER TABLE binned ADD COLUMN grid_l1_w REAL")
        if "grid_l2_w" not in columns:
            conn.execute("ALTER TABLE binned ADD COLUMN grid_l2_w REAL")
        if "grid_l3_w" not in columns:
            conn.execute("ALTER TABLE binned ADD COLUMN grid_l3_w REAL")
        conn.commit()


def insert_measurements(db_path: str, rows: Iterable[Tuple[str, str, Optional[float]]]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO measurements (ts_utc, entity_id, value) VALUES (?, ?, ?)",
            list(rows),
        )
        conn.commit()


def upsert_binned(
    db_path: str,
    ts_local_bin_start: str,
    total_w: Optional[float],
    l1_w: Optional[float],
    l2_w: Optional[float],
    l3_w: Optional[float],
    grid_l1_w: Optional[float],
    grid_l2_w: Optional[float],
    grid_l3_w: Optional[float],
    inverter_w: Optional[float],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO binned (ts_local_bin_start, total_w, l1_w, l2_w, l3_w, grid_l1_w, grid_l2_w, grid_l3_w, inverter_w)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts_local_bin_start, total_w, l1_w, l2_w, l3_w, grid_l1_w, grid_l2_w, grid_l3_w, inverter_w),
        )
        conn.commit()


def fetch_binned_since(db_path: str, ts_local_start: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ts_local_bin_start, total_w, l1_w, l2_w, l3_w, grid_l1_w, grid_l2_w, grid_l3_w, inverter_w
            FROM binned
            WHERE ts_local_bin_start >= ?
            ORDER BY ts_local_bin_start ASC
            """,
            (ts_local_start,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_binned_between(db_path: str, start_local: str, end_local: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ts_local_bin_start, total_w, l1_w, l2_w, l3_w, grid_l1_w, grid_l2_w, grid_l3_w, inverter_w
            FROM binned
            WHERE ts_local_bin_start >= ? AND ts_local_bin_start < ?
            ORDER BY ts_local_bin_start ASC
            """,
            (start_local, end_local),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_points_count(db_path: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()
    return int(row[0]) if row else 0


def get_metadata(db_path: str, key: str) -> Optional[str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_metadata(db_path: str, key: str, value: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


def fetch_ilc_curve(db_path: str, signal: str) -> Dict[int, float]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT bin, value FROM ilc_curve WHERE signal = ?",
            (signal,),
        ).fetchall()
    return {int(bin_index): float(value) for bin_index, value in rows}


def save_ilc_curve(db_path: str, signal: str, curve: Dict[int, float]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO ilc_curve (signal, bin, value) VALUES (?, ?, ?)",
            [(signal, int(bin_index), float(value)) for bin_index, value in curve.items()],
        )
        conn.commit()


def fetch_latest_measurements(db_path: str) -> Dict[str, Any]:
    """Fetch the most recent measurements (latest poll timestamp)."""
    with sqlite3.connect(db_path) as conn:
        # Get the latest timestamp
        row = conn.execute(
            "SELECT MAX(ts_utc) FROM measurements"
        ).fetchone()

        if not row or row[0] is None:
            return {"ts_utc": None, "values": {}}

        latest_ts = row[0]

        # Get all measurements at that timestamp
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entity_id, value FROM measurements WHERE ts_utc = ?",
            (latest_ts,)
        ).fetchall()

        values = {row["entity_id"]: row["value"] for row in rows}

        return {
            "ts_utc": latest_ts,
            "values": values
        }


def fetch_avg_for_entity(
    db_path: str, entity_id: str, start_utc_iso: str, end_utc_iso: str
) -> Optional[float]:
    """
    Compute the average value for an entity over a UTC time range.
    Uses lexical comparison on ISO timestamp strings.
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT AVG(value) FROM measurements
            WHERE entity_id = ? AND ts_utc >= ? AND ts_utc < ?
            """,
            (entity_id, start_utc_iso, end_utc_iso),
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def fetch_avg_for_multiple_entities(
    db_path: str, entity_ids: List[str], start_utc_iso: str, end_utc_iso: str
) -> Dict[str, Optional[float]]:
    """
    Compute averages for multiple entities in one query for efficiency.
    """
    if not entity_ids:
        return {}

    placeholders = ",".join("?" * len(entity_ids))
    with sqlite3.connect(db_path) as conn:
        query = f"""
            SELECT entity_id, AVG(value) as avg_value
            FROM measurements
            WHERE entity_id IN ({placeholders}) AND ts_utc >= ? AND ts_utc < ?
            GROUP BY entity_id
        """
        rows = conn.execute(
            query, (*entity_ids, start_utc_iso, end_utc_iso)
        ).fetchall()

    result = {entity_id: None for entity_id in entity_ids}
    for entity_id, avg_value in rows:
        result[entity_id] = float(avg_value) if avg_value is not None else None
    return result


def save_daily_forecast(
    db_path: str,
    date_local: str,
    created_local: str,
    forecast_dict_by_signal: Dict[str, Dict[int, float]],
) -> None:
    """
    Save a frozen forecast for a specific date.
    forecast_dict_by_signal: {"total_w": {bin: value, ...}, "l1_w": {...}, ...}
    """
    rows = []
    for signal, bins in forecast_dict_by_signal.items():
        for bin_idx, value in bins.items():
            rows.append((date_local, signal, int(bin_idx), float(value), created_local))

    with sqlite3.connect(db_path) as conn:
        # Delete existing forecast for this date (if any)
        conn.execute("DELETE FROM daily_forecast WHERE date_local = ?", (date_local,))
        # Insert new forecast
        conn.executemany(
            "INSERT INTO daily_forecast (date_local, signal, bin, value, created_local) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def load_daily_forecast(db_path: str, date_local: str) -> Dict[str, Dict[int, float]]:
    """
    Load a frozen forecast for a specific date.
    Returns: {"total_w": {bin: value}, "l1_w": {...}, ...}
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT signal, bin, value FROM daily_forecast WHERE date_local = ?",
            (date_local,),
        ).fetchall()

    result: Dict[str, Dict[int, float]] = {}
    for signal, bin_idx, value in rows:
        if signal not in result:
            result[signal] = {}
        result[signal][int(bin_idx)] = float(value)
    return result


def daily_forecast_exists(db_path: str, date_local: str) -> bool:
    """Check if a frozen forecast exists for the given date."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_forecast WHERE date_local = ?",
            (date_local,),
        ).fetchone()
    return row[0] > 0 if row else False


def save_daily_forecast_metrics(
    db_path: str,
    date_local: str,
    signal: str,
    mae: float,
    mape: float,
    accuracy_pct: float,
    n_bins_compared: int,
    created_local: str,
) -> None:
    """Save accuracy metrics for a completed day's forecast."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_forecast_metrics
            (date_local, signal, mae, mape, accuracy_pct, n_bins_compared, created_local)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (date_local, signal, mae, mape, accuracy_pct, n_bins_compared, created_local),
        )
        conn.commit()


def load_daily_forecast_metrics(
    db_path: str, date_local: str
) -> Optional[Dict[str, Any]]:
    """Load accuracy metrics for a specific date."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT signal, mae, mape, accuracy_pct, n_bins_compared, created_local
            FROM daily_forecast_metrics WHERE date_local = ?
            """,
            (date_local,),
        ).fetchone()
    return dict(row) if row else None
