from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import os


@dataclass
class EntityConfig:
    total_load_power: str | None
    l1_load_power: str | None
    l2_load_power: str | None
    l3_load_power: str | None
    soc: str | None
    grid_l1_current: str | None
    grid_l2_current: str | None
    grid_l3_current: str | None


@dataclass
class AppConfig:
    ha_url: str
    ha_token: str
    poll_interval_minutes: int
    timezone: str
    horizon_hours: int
    entities: EntityConfig
    db_path: str


def normalize_entity_id(s: str | None) -> str | None:
    """Normalize entity ID from config, treating various forms as disabled."""
    if s is None:
        return None
    s = s.strip()
    # Remove surrounding quotes if present (e.g. '" "' becomes ' ' then empty)
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    # Treat empty string, None, "none", "null", "disabled" (case-insensitive) as DISABLED
    if s == "" or s.lower() in {"none", "null", "disabled"}:
        return None
    return s


def _optional_env(name: str) -> str | None:
    """Read optional environment variable with normalization."""
    value = os.environ.get(name)
    return normalize_entity_id(value)


def load_config() -> AppConfig:
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    return AppConfig(
        ha_url=os.environ.get("HA_URL", "http://supervisor/core"),
        ha_token=os.environ.get("HA_TOKEN", supervisor_token),
        poll_interval_minutes=int(os.environ.get("POLL_INTERVAL_MINUTES", "15")),
        timezone=os.environ.get("TIMEZONE", "Europe/Stockholm"),
        horizon_hours=int(os.environ.get("HORIZON_HOURS", "48")),
        entities=EntityConfig(
            total_load_power=normalize_entity_id(os.environ.get("ENTITY_TOTAL_LOAD_POWER", "")),
            l1_load_power=normalize_entity_id(os.environ.get("ENTITY_L1_LOAD_POWER", "")),
            l2_load_power=normalize_entity_id(os.environ.get("ENTITY_L2_LOAD_POWER", "")),
            l3_load_power=normalize_entity_id(os.environ.get("ENTITY_L3_LOAD_POWER", "")),
            soc=_optional_env("ENTITY_SOC"),
            grid_l1_current=_optional_env("ENTITY_GRID_L1_CURRENT"),
            grid_l2_current=_optional_env("ENTITY_GRID_L2_CURRENT"),
            grid_l3_current=_optional_env("ENTITY_GRID_L3_CURRENT"),
        ),
        db_path=os.environ.get("DB_PATH", "/data/energyhome.sqlite"),
    )
