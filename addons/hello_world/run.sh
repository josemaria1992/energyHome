#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting Hello World add-on v0.1.0"
bashio::log.info "Hello World"
while true; do
  sleep 30
  bashio::log.info "Hello World"
done
