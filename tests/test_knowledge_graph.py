"""
Unit tests for Knowledge Graph extraction and graph traversal search in Hermes Fleet Memory.
"""
import unittest

import fleet_memory

from client.knowledge_graph import extract_entities_and_relations


class TestKnowledgeGraph(unittest.TestCase):

    def test_entity_and_relation_extraction(self):
        text = "Hermes Fleet Memory runs on [[Qdrant]] and integrates with `FastMCP` to serve Claude Desktop."
        entities, relations = extract_entities_and_relations(text)

        self.assertIn("Qdrant", entities)
        self.assertIn("FastMCP", entities)
        self.assertTrue(any(e in entities for e in ["Hermes Fleet Memory", "Claude Desktop"]))
        self.assertTrue(len(relations) > 0)

    def test_fleet_graph_query_structure(self):
        # Test graph traversal execution
        res = fleet_memory.fleet_graph_query(entity="Qdrant", limit=3)
        self.assertEqual(res["entity"], "Qdrant")
        self.assertIn("connected_entities", res)
        self.assertIn("relations", res)
        self.assertIn("memories", res)


def _fill(db, n, hit_at):
    for i in range(n):
        text = "Winston runs on the RTX rig" if i in hit_at else f"unrelated card {i}"
        db.points[f"p{i}"] = {"id": f"p{i}", "vector": None,
                              "payload": {"text": text, "domain": "shared", "status": "active"}}


def test_graph_query_reaches_cards_past_the_first_page(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    _fill(mock_fleet_memory_engine, 600, hit_at={590})

    res = fleet_memory.fleet_graph_query(entity="Winston", limit=5)

    assert res["matched_memories_count"] == 1
    assert res["memories"][0]["id"] == "p590"
    assert res["scanned_points"] == 600
    assert res["truncated"] is False


def test_graph_query_reports_when_the_scan_cap_cuts_it_short(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    monkeypatch.setenv("FLEET_GRAPH_SCAN_LIMIT", "300")
    _fill(mock_fleet_memory_engine, 600, hit_at={590})

    res = fleet_memory.fleet_graph_query(entity="Winston", limit=5)

    assert res["matched_memories_count"] == 0
    assert res["scanned_points"] == 300
    assert res["truncated"] is True


if __name__ == "__main__":
    unittest.main()
