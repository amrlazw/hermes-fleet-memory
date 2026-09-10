"""
Episodic Memory Cleaner Tests:
Verifies JSONL archival dump and hard physical eviction from Qdrant HNSW RAM index.
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# Import cleaner from server/
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
import cleaner


class DummyPoint:
    def __init__(self, id, payload):
        self.id = id
        self.payload = payload


def test_archive_points(tmp_path, monkeypatch):
    """Verifies that expired points are safely written to JSONL before deletion."""
    archive_dir = tmp_path / "archives"
    monkeypatch.setattr(cleaner, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(cleaner, "ARCHIVE_FILE", archive_dir / "archived.jsonl")

    sample_points = [
        DummyPoint("uuid-1", {"text": "Temporary note 1", "expires_at": 1000}),
        DummyPoint("uuid-2", {"text": "Temporary note 2", "expires_at": 2000})
    ]

    cleaner.archive_points(sample_points)

    assert (archive_dir / "archived.jsonl").exists()
    lines = (archive_dir / "archived.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    rec1 = json.loads(lines[0])
    assert rec1["id"] == "uuid-1"
    assert rec1["payload"]["text"] == "Temporary note 1"
    assert "archived_at" in rec1


def test_clean_expired_memories_performs_hard_deletion(tmp_path, monkeypatch):
    """Verifies that cleaner invokes client.delete() with the expired point IDs."""
    archive_dir = tmp_path / "archives"
    monkeypatch.setattr(cleaner, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(cleaner, "ARCHIVE_FILE", archive_dir / "archived.jsonl")

    mock_client = MagicMock()
    mock_client.scroll.return_value = (
        [DummyPoint("uuid-101", {"status": "active", "expires_at": 100})],
        None
    )
    monkeypatch.setattr(cleaner, "QdrantClient", lambda **kwargs: mock_client)

    cleaner.clean_expired_memories()

    # Verify client.delete was called with the point ID
    assert mock_client.delete.called
    call_kwargs = mock_client.delete.call_args[1]
    assert call_kwargs["collection_name"] == cleaner.COLLECTION_NAME
    point_ids = call_kwargs["points_selector"].points
    assert point_ids == ["uuid-101"]
