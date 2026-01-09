#!/usr/bin/with-contenv bashio

bashio::log.info "Hello World"
while true; do
  sleep 30
  bashio::log.info "Hello World"
done
