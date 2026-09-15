#!/usr/bin/env python3
"""
hermes-fleet-memory: Episodic Memory Purger & Archive Engine
Runs periodically (e.g. weekly via cron) on the central server to physically evict
expired episodic vectors from Qdrant HNSW RAM index and archive them to disk.
"""

import json
import os
import time
from pathlib import Path

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
except ImportError:
    QdrantClient = None
    class DummyModels:
        class PointIdsList:
            def __init__(self, points):
                self.points = points
        class FieldCondition:
            def __init__(self, **kwargs): pass
        class MatchValue:
            def __init__(self, **kwargs): pass
        class Range:
            def __init__(self, **kwargs): pass
        class Filter:
            def __init__(self, **kwargs): pass
    models = DummyModels()

COLLECTION_NAME = os.getenv("FLEET_COLLECTION_NAME", "hermes_fleet_memory")
QDRANT_HOST = os.getenv("FLEET_QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("FLEET_QDRANT_PORT", "6333"))
QDRANT_KEY = os.getenv("FLEET_QDRANT_KEY", None)
QDRANT_TIMEOUT = float(os.getenv("FLEET_QDRANT_TIMEOUT", "30"))
BATCH_SIZE = int(os.getenv("FLEET_CLEANER_BATCH_SIZE", "500"))

ARCHIVE_DIR = Path(os.getenv("FLEET_ARCHIVE_DIR", os.path.expanduser("~/.hermes/archives")))
ARCHIVE_FILE = ARCHIVE_DIR / "expired_episodic_memories.jsonl"


def archive_points(points):
    """Safely append expired points to an offline JSONL audit file before RAM eviction."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_FILE, "a", encoding="utf-8") as f:
        for pt in points:
            record = {
                "id": str(pt.id),
                "payload": pt.payload,
                "archived_at": int(time.time()),
                "archived_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def clean_expired_memories():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_KEY,
                          timeout=QDRANT_TIMEOUT, check_compatibility=False)
    now = int(time.time())

    # Find active, unpinned points past their expiration timestamp
    expired_filter = models.Filter(
        must=[
            models.FieldCondition(key="status", match=models.MatchValue(value="active")),
            models.FieldCondition(key="pinned", match=models.MatchValue(value=False)),
            models.FieldCondition(key="expires_at", range=models.Range(gt=0, lt=now))
        ]
    )

    # Drain every expired point, not just the first page. A single scroll(limit=500)
    # silently left any overflow in the index until the next scheduled run, with
    # nothing reporting the backlog. Deleted points stop matching the filter, so
    # re-scrolling from the start advances; MAX_BATCHES bounds the loop in case a
    # delete fails and the same page keeps coming back.
    MAX_BATCHES = 200
    total_archived = 0

    for batch in range(MAX_BATCHES):
        expired_points = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=expired_filter,
            limit=BATCH_SIZE,
            with_payload=True,
            with_vectors=False
        )[0]

        if not expired_points:
            break

        archive_points(expired_points)
        point_ids = [pt.id for pt in expired_points]
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=point_ids)
        )
        total_archived += len(point_ids)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Batch {batch + 1}: archived and evicted "
              f"{len(point_ids)} points.")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: stopped after {MAX_BATCHES} batches. "
              f"Expired points may remain -- check that deletes are succeeding.")

    if total_archived == 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No expired memories found.")
        return

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Archived {total_archived} records to {ARCHIVE_FILE}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Evicted {total_archived} points from "
          f"'{COLLECTION_NAME}' HNSW graph.")


if __name__ == "__main__":
    clean_expired_memories()
