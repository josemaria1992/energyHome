from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger("energyhome")


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
    """Load configuration with deterministic auth mode selection."""
    # 1) Normalize ha_url
    base_url = os.environ.get("HA_URL", "").strip()
    base_url = base_url.rstrip("/")  # remove trailing slash to avoid //api/...

    # 2) Normalize ha_token
    token_cfg = os.environ.get("HA_TOKEN", "").strip()

    # 3) Choose auth mode deterministically
    if token_cfg:
        # Mode A: Manual token mode
        token = token_cfg
        if not base_url:
            base_url = "http://homeassistant:8123"
        logger.info("HA auth mode: manual token -> using %s", base_url)
    else:
        # Mode B: Supervisor token mode (no manual token)
        supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not supervisor_token:
            raise ValueError(
                "HA auth failed: ha_token is empty and SUPERVISOR_TOKEN not available. "
                "Please set ha_token in add-on configuration."
            )
        token = supervisor_token
        base_url = "http://supervisor/core"
        logger.info("HA auth mode: supervisor token (ha_token empty) -> using http://supervisor/core")

    return AppConfig(
        ha_url=base_url,
        ha_token=token,
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
