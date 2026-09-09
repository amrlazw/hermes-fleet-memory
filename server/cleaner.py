#!/usr/bin/env python3
"""
hermes-fleet-memory: Episodic Tombstone Cleaner
Runs periodically (e.g. weekly via cron) on the central server to mark expired
episodic vectors as tombstones and maintain vector database hygiene.
"""

import os
import time
import sys
from qdrant_client import QdrantClient
from qdrant_client.http import models

COLLECTION_NAME = "hermes_fleet_memory"
QDRANT_HOST = os.getenv("FLEET_QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("FLEET_QDRANT_PORT", "6333"))
QDRANT_KEY = os.getenv("FLEET_QDRANT_KEY", None)


def clean_expired_memories():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_KEY, check_compatibility=False)
    now = int(time.time())

    # Find active, unpinned points past their expiration timestamp
    expired_filter = models.Filter(
        must=[
            models.FieldCondition(key="status", match=models.MatchValue(value="active")),
            models.FieldCondition(key="pinned", match=models.MatchValue(value=False)),
            models.FieldCondition(key="expires_at", range=models.Range(gt=0, lt=now))
        ]
    )

    scroll_result = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=expired_filter,
        limit=500,
        with_payload=True,
        with_vectors=False
    )

    expired_points = scroll_result[0]
    if not expired_points:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No expired memories found.")
        return

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Purging {len(expired_points)} expired episodic memories...")
    for pt in expired_points:
        client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"status": "tombstone", "purged_at": now},
            points=[pt.id]
        )

    print("Cleanup cycle complete.")


if __name__ == "__main__":
    clean_expired_memories()
