#!/usr/bin/env bash
# hermes-fleet-memory: Linux / macOS client tunnel launcher
set -euo pipefail

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

SERVER_HOST="${FLEET_SERVER_HOST:-brain.example.com}"
FLEET_KEY="${FLEET_QDRANT_KEY:-}"

if [ -z "$FLEET_KEY" ]; then
    echo "Error: FLEET_QDRANT_KEY is not set in .env"
    exit 1
fi

echo "Starting wstunnel client connecting to wss://${SERVER_HOST}/tunnel..."

# Forward local port 6333 to VPS Qdrant, and optionally reverse bridge port 8099
wstunnel client \
    -L tcp://127.0.0.1:6333:127.0.0.1:6333 \
    -R tcp://127.0.0.1:8099:127.0.0.1:8099 \
    --http-headers "X-Fleet-Key: ${FLEET_KEY}" \
    --websocket-ping-frequency 20s \
    -P tunnel \
    "wss://${SERVER_HOST}"
