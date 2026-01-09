#!/usr/bin/env bash
set -euo pipefail

BUILD_FROM=${BUILD_FROM:-ghcr.io/home-assistant/amd64-base:latest}
rgyhome_forecast"

IMAGE_NAME=${IMAGE_NAME:-energyhome-hello-world}

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

cd "${ROOT_DIR}/addons/hello_world"

docker build \
  --build-arg BUILD_FROM="${BUILD_FROM}" \
  -t "${IMAGE_NAME}" \
  .

echo "Built ${IMAGE_NAME} using ${BUILD_FROM}"
