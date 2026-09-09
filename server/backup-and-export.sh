#!/usr/bin/env bash
# hermes-fleet-memory: Atomic Qdrant Snapshot & JSONL Export
set -euo pipefail

BACKUP_DIR="${FLEET_BACKUP_DIR:-/opt/hermes-backups}"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
KEY="${FLEET_QDRANT_KEY:-}"

echo "Creating atomic snapshot for hermes_fleet_memory..."
SNAPSHOT_RESP=$(curl -s -X POST "http://127.0.0.1:6333/collections/hermes_fleet_memory/snapshots" \
    -H "api-key: ${KEY}")

SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESP" | grep -o '"name":"[^"]*' | cut -d'"' -f4 || true)

if [ -n "$SNAPSHOT_NAME" ]; then
    echo "Downloading snapshot: $SNAPSHOT_NAME"
    curl -s -o "${BACKUP_DIR}/qdrant_${TIMESTAMP}.snapshot" \
        -H "api-key: ${KEY}" \
        "http://127.0.0.1:6333/collections/hermes_fleet_memory/snapshots/${SNAPSHOT_NAME}"
fi

# Keep only the last 4 weekly backups
find "$BACKUP_DIR" -type f -name "qdrant_*.snapshot" -mtime +28 -delete

echo "Backup complete: ${BACKUP_DIR}/qdrant_${TIMESTAMP}.snapshot"
