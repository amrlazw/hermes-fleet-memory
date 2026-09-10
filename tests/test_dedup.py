"""
Episodic Semantic Deduplication & Epistemic Attribution Tests:
Verifies that near-identical episodic memories (cosine similarity >= 0.95)
update in-place rather than bloating the index, and checks author_node attribution.
"""

import os
import fleet_memory


class DummyPoint:
    def __init__(self, id, payload, score=0.98):
        self.id = id
        self.payload = payload
        self.score = score


def test_provenance_attribution(monkeypatch):
    """Verifies that author_node and revision are attached to all stored memories."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    monkeypatch.setenv("FLEET_NODE_NAME", "winston")

    res = fleet_memory.fleet_memory_store(
        text="Authoritative hardware baseline test",
        client_id="hardware",
        slot_name="profile_test"
    )

    assert res["status"] == "success"
    assert res["author_node"] == "winston"
    assert res["revision"] >= 1


def test_semantic_dedup_updates_existing_point(monkeypatch):
    """Verifies that when a near-verbatim semantic match exists, it updates in-place."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")
    monkeypatch.setenv("FLEET_NODE_NAME", "winston")

    mock_client = fleet_memory.get_client()
    existing_match = DummyPoint(
        id="existing-uuid-1234",
        payload={"revision": 2, "updated_at": 1000.0, "text": "Wolf proxy healthy"}
    )
    # Mock query_points to return the near duplicate
    monkeypatch.setattr(mock_client, "query_points", lambda **kwargs: [existing_match])

    res = fleet_memory.fleet_memory_store(
        text="Wolf proxy healthy and verified",
        target_domain="personal"
    )

    assert res["status"] == "success"
    assert res["id"] == "existing-uuid-1234"
    assert res["mode"] == "semantic_dedup_update"
    assert res["revision"] == 3
