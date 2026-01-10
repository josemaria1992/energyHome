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
