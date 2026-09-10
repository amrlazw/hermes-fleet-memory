#!/usr/bin/env bash
# hermes-fleet-memory: Linux / macOS resilient client tunnel launcher
# Implements exponential backoff with jitter against network disruptions and server restarts.
set -euo pipefail

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
elif [ -f ~/.hermes/.env ]; then
    export $(grep -v '^#' ~/.hermes/.env | xargs)
fi

SERVER_HOST="${FLEET_SERVER_HOST:-brain.example.com}"
FLEET_KEY="${FLEET_QDRANT_KEY:-}"

if [ -z "$FLEET_KEY" ]; then
    echo "Error: FLEET_QDRANT_KEY is not set in environment or .env"
    exit 1
fi

INITIAL_DELAY=2
MAX_DELAY=60
BACKOFF=$INITIAL_DELAY

echo "=========================================================="
echo " Starting Hermes Fleet Tunnel (Resilient WSTunnel Mesh)"
echo " Connecting to: wss://${SERVER_HOST}"
echo "=========================================================="

while true; do
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Connecting tunnel..."
    
    # Forward local port 6333 to VPS Qdrant, and reverse bridge port 8099
    wstunnel client \
        -L tcp://127.0.0.1:6333:127.0.0.1:6333 \
        -R tcp://127.0.0.1:8099:127.0.0.1:8099 \
        --http-headers "X-Fleet-Key: ${FLEET_KEY}" \
        --websocket-ping-frequency 20s \
        -P tunnel \
        "wss://${SERVER_HOST}" || EXIT_CODE=$?

    # Calculate jitter (0 to 3 seconds)
    JITTER=$(( RANDOM % 4 ))
    SLEEP_TIME=$(( BACKOFF + JITTER ))
    
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Tunnel disconnected (code: ${EXIT_CODE:-0}). Reconnecting in ${SLEEP_TIME}s..."
    sleep $SLEEP_TIME

    # Exponential backoff doubling up to MAX_DELAY
    BACKOFF=$(( BACKOFF * 2 ))
    if [ $BACKOFF -gt $MAX_DELAY ]; then
        BACKOFF=$MAX_DELAY
    fi
done
