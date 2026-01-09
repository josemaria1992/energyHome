#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting EnergyHome Forecast add-on v0.2.0"

export HA_URL
HA_URL="$(bashio::config 'ha_url')"
export HA_TOKEN
HA_TOKEN="$(bashio::config 'ha_token')"
export POLL_INTERVAL_MINUTES
POLL_INTERVAL_MINUTES="$(bashio::config 'poll_interval_minutes')"
export TIMEZONE
TIMEZONE="$(bashio::config 'timezone')"
export HORIZON_HOURS
HORIZON_HOURS="$(bashio::config 'horizon_hours')"
export ENTITY_TOTAL_LOAD_POWER
ENTITY_TOTAL_LOAD_POWER="$(bashio::config 'entities.total_load_power')"
export ENTITY_L1_LOAD_POWER
ENTITY_L1_LOAD_POWER="$(bashio::config 'entities.l1_load_power')"
export ENTITY_L2_LOAD_POWER
ENTITY_L2_LOAD_POWER="$(bashio::config 'entities.l2_load_power')"
export ENTITY_L3_LOAD_POWER
ENTITY_L3_LOAD_POWER="$(bashio::config 'entities.l3_load_power')"
export ENTITY_SOC
ENTITY_SOC="$(bashio::config 'entities.soc')"
export ENTITY_GRID_L1_CURRENT
ENTITY_GRID_L1_CURRENT="$(bashio::config 'entities.grid_l1_current')"
export ENTITY_GRID_L2_CURRENT
ENTITY_GRID_L2_CURRENT="$(bashio::config 'entities.grid_l2_current')"
export ENTITY_GRID_L3_CURRENT
ENTITY_GRID_L3_CURRENT="$(bashio::config 'entities.grid_l3_current')"
export DB_PATH
DB_PATH="/data/energyhome.sqlite"

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
