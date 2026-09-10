"""
Pytest fixtures and in-memory mock engine for hermes-fleet-memory testing.
Provides mock vector embeddings and mock Qdrant storage without network dependencies.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "client"))


class MockEmbedder:
    """Deterministic mock embedding generator (384-dimensional vector)."""
    def embed(self, texts):
        results = []
        for text in texts:
            # Deterministic pseudo-vector based on hash of text
            val = float(abs(hash(text)) % 1000) / 1000.0
            vec = [val] * 384
            results.append(vec)
        return results


class MockQdrantStorage:
    """In-memory point store mimicking QdrantClient."""
    def __init__(self):
        self.points = {}  # id -> {id, vector, payload}

    def upsert(self, collection_name, points):
        for p in points:
            self.points[p.id] = {
                "id": p.id,
                "vector": p.vector,
                "payload": p.payload
            }

    def retrieve(self, collection_name, ids, with_payload=True):
        results = []
        for pid in ids:
            if pid in self.points:
                m = MagicMock()
                m.id = pid
                m.payload = self.points[pid]["payload"]
                results.append(m)
        return results

    def query_points(self, collection_name, query, query_filter=None, limit=5, with_payload=True):
        class PointsResult:
            def __init__(self, items):
                self.points = items

        items = []
        for pid, data in self.points.items():
            payload = data["payload"]
            # Simple domain match simulation
            m = MagicMock()
            m.id = pid
            m.score = 0.95
            m.payload = payload
            items.append(m)
        return PointsResult(items[:limit])

    def get_collections(self):
        m = MagicMock()
        col = MagicMock()
        col.name = "hermes_fleet_memory"
        m.collections = [col]
        return m


@pytest.fixture(autouse=True)
def mock_fleet_memory_engine(monkeypatch):
    """Auto-mock Qdrant client and FastEmbed model for deterministic offline testing."""
    import fleet_memory

    mock_db = MockQdrantStorage()
    mock_emb = MockEmbedder()

    monkeypatch.setattr(fleet_memory, "get_client", lambda: mock_db)
    monkeypatch.setattr(fleet_memory, "get_embedder", lambda: mock_emb)

    return mock_db
