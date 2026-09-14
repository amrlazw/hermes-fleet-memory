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


if __name__ == "__main__":
    unittest.main()
