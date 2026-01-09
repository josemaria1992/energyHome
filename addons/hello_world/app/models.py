from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import os


@dataclass
class EntityConfig:
    total_load_power: str
    l1_load_power: str
    l2_load_power: str
    l3_load_power: str
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


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if not value or value.lower() in {"none", "null"}:
        return None
    return value


def load_config() -> AppConfig:
    return AppConfig(
        ha_url=os.environ.get("HA_URL", "http://homeassistant.local:8123"),
        ha_token=os.environ.get("HA_TOKEN", ""),
        poll_interval_minutes=int(os.environ.get("POLL_INTERVAL_MINUTES", "15")),
        timezone=os.environ.get("TIMEZONE", "Europe/Stockholm"),
        horizon_hours=int(os.environ.get("HORIZON_HOURS", "48")),
        entities=EntityConfig(
            total_load_power=os.environ.get("ENTITY_TOTAL_LOAD_POWER", ""),
            l1_load_power=os.environ.get("ENTITY_L1_LOAD_POWER", ""),
            l2_load_power=os.environ.get("ENTITY_L2_LOAD_POWER", ""),
            l3_load_power=os.environ.get("ENTITY_L3_LOAD_POWER", ""),
            soc=_optional_env("ENTITY_SOC"),
            grid_l1_current=_optional_env("ENTITY_GRID_L1_CURRENT"),
            grid_l2_current=_optional_env("ENTITY_GRID_L2_CURRENT"),
            grid_l3_current=_optional_env("ENTITY_GRID_L3_CURRENT"),
        ),
        db_path=os.environ.get("DB_PATH", "/data/energyhome.sqlite"),
    )
