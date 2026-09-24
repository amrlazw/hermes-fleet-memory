"""
Unit tests for all FastMCP tool functions to satisfy M8ven and OpenAI directory test coverage.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure client module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client")))


class TestMCPToolsCoverage(unittest.TestCase):

    def setUp(self):
        import fleet_memory
        if not getattr(fleet_memory, "HAS_MCP", False):
            self.skipTest("FastMCP is not installed in the test environment")
        os.environ["FLEET_HARD_DOMAIN"] = "all"
        os.environ["FLEET_KEY"] = "test_key"
        os.environ["FLEET_TASKS_URL"] = "http://127.0.0.1:8000"
        # Keys are resolved at import time, so set the bridge key on the module.
        bridge_key = patch.object(fleet_memory, "FLEET_BRIDGE_KEY", "bridge_test_key")
        bridge_key.start()
        self.addCleanup(bridge_key.stop)

    @patch("urllib.request.urlopen")
    def test_desktop_status(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "online", "gpu": "RTX 3070 Ti"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fleet_memory.desktop_status()
        self.assertEqual(res.get("status"), "online")

    @patch("urllib.request.urlopen")
    def test_desktop_exec(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "success", "stdout": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fleet_memory.desktop_exec(command="echo ok")
        self.assertEqual(res.get("status"), "success")

    @patch("urllib.request.urlopen")
    def test_desktop_read_file(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "success", "content": "file_data"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fleet_memory.desktop_read_file(path="test.txt")
        self.assertEqual(res.get("status"), "success")

    @patch("urllib.request.urlopen")
    def test_desktop_download_file(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b'chunk1', b'']
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch("builtins.open", unittest.mock.mock_open()), \
             patch("os.path.getsize", return_value=6), \
             patch("os.makedirs"):
            res = fleet_memory.desktop_download_file(remote_path="test.pdf", local_destination="/tmp/test.pdf")
            self.assertEqual(res.get("status"), "success")

    @patch("fleet_memory.desktop_download_file")
    @patch("urllib.request.urlopen")
    def test_desktop_archive_folder(self, mock_urlopen, mock_download):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "success", "archive_path": "C:/tmp/archive.zip"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        mock_download.return_value = {"status": "success", "size_bytes": 100}

        res = fleet_memory.desktop_archive_folder(remote_dir="C:/test")
        self.assertEqual(res.get("status"), "success")

    @patch("urllib.request.urlopen")
    def test_desktop_power(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "scheduled", "action": "shutdown"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fleet_memory.desktop_power(action="shutdown", delay_seconds=10)
        self.assertEqual(res.get("status"), "scheduled")

    @patch("urllib.request.urlopen")
    def test_fleet_task_delegate(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"task_id": "tsk_123", "status": "pending"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(fleet_memory, "FLEET_TASKS_URL", "http://127.0.0.1:8000"), \
                patch.object(fleet_memory, "FLEET_KEY", "test_key"):
            res = fleet_memory.fleet_task_delegate(target_node="chester", action="telegram_notify", params={"message": "hi"})
        self.assertEqual(res.get("status"), "accepted")
        self.assertEqual(res.get("task_id"), "tsk_123")

    @patch("urllib.request.urlopen")
    def test_fleet_task_status(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"task_id": "tsk_123", "status": "completed", "result": {"output": "done"}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(fleet_memory, "FLEET_TASKS_URL", "http://127.0.0.1:8000"), \
                patch.object(fleet_memory, "FLEET_KEY", "test_key"):
            res = fleet_memory.fleet_task_status(task_id="tsk_123", verify_receipt=False)
        self.assertEqual(res.get("status"), "completed")

    @patch("urllib.request.urlopen")
    def test_task_plane_requires_explicit_endpoint(self, mock_urlopen):
        """An unconfigured node must refuse locally instead of calling any hub."""
        import fleet_memory
        with patch.object(fleet_memory, "FLEET_TASKS_URL", ""), \
                patch.object(fleet_memory, "FLEET_KEY", "test_key"):
            delegated = fleet_memory.fleet_task_delegate(target_node="node-a", action="fleet_health_ping")
            queried = fleet_memory.fleet_task_status(task_id="tsk_123")

        for res in (delegated, queried):
            self.assertEqual(res.get("status"), "error")
            self.assertIn("FLEET_TASKS_URL", res.get("message", ""))
        mock_urlopen.assert_not_called()

    @patch("fleet_memory.get_client")
    def test_fleet_graph_search(self, mock_client):
        import fleet_memory
        mock_point = MagicMock()
        mock_point.id = "p-1"
        mock_point.payload = {
            "domain": "shared",
            "client_id": "test",
            "slot_name": "graph_test",
            "text": "FastMCP communicates with Qdrant vector database",
            "entities": ["FastMCP", "Qdrant"],
            "relations": [{"source": "FastMCP", "relation": "communicates_with", "target": "Qdrant"}]
        }
        mock_client.return_value.scroll.return_value = ([mock_point], None)

        res = fleet_memory.fleet_graph_query(entity="Qdrant")
        self.assertEqual(res["entity"], "Qdrant")
        self.assertIn("FastMCP", res["connected_entities"])
        self.assertEqual(res["matched_memories_count"], 1)

    @patch("fleet_memory.get_client")
    @patch("fleet_memory.get_embedder")
    def test_fleet_memory_search_tool(self, mock_get_embedder, mock_client):
        import fleet_memory
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.1] * 384]
        mock_get_embedder.return_value = mock_embedder
        mock_hit = MagicMock()
        mock_hit.score = 0.95
        mock_hit.payload = {"text": "Architecture note", "domain": "shared"}
        mock_client.return_value.query_points.return_value.points = [mock_hit]

        res = fleet_memory.fleet_memory_search(query="architecture")
        self.assertIsInstance(res, list)
        self.assertEqual(res[0]["text"], "Architecture note")

    @patch("fleet_memory.get_client")
    @patch("fleet_memory.get_embedder")
    def test_fleet_memory_store_tool(self, mock_get_embedder, mock_client):
        import fleet_memory
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.1] * 384]
        mock_get_embedder.return_value = mock_embedder
        mock_client.return_value.upsert.return_value = MagicMock()

        res = fleet_memory.fleet_memory_store(text="New architectural decision")
        self.assertEqual(res.get("status"), "success")


if __name__ == "__main__":
    unittest.main()


class TestKeySeparation(unittest.TestCase):
    """The bridge, the control plane and Qdrant each get their own credential."""

    DESKTOP_CALLS = (
        ("desktop_status", {}),
        ("desktop_exec", {"command": "echo ok"}),
        ("desktop_read_file", {"path": "a.txt"}),
        ("desktop_download_file", {"remote_path": "a.pdf", "local_destination": "/tmp/a.pdf"}),
        ("desktop_archive_folder", {"remote_dir": "C:/x"}),
        ("desktop_power", {"action": "cancel"}),
    )

    def setUp(self):
        import fleet_memory
        if not getattr(fleet_memory, "HAS_MCP", False):
            self.skipTest("FastMCP is not installed in the test environment")

    @patch("urllib.request.urlopen")
    def test_desktop_tools_send_the_bridge_key_not_the_qdrant_key(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(fleet_memory, "FLEET_BRIDGE_KEY", "bridge-secret"), \
                patch.object(fleet_memory, "QDRANT_API_KEY", "qdrant-secret"):
            fleet_memory.desktop_status()
            fleet_memory.desktop_power(action="cancel")

        headers = [c.args[0].get_header("Authorization") for c in mock_urlopen.call_args_list]
        self.assertEqual(headers, ["Bearer bridge-secret", "Bearer bridge-secret"])

    @patch("urllib.request.urlopen")
    def test_desktop_tools_refuse_without_a_bridge_key(self, mock_urlopen):
        import fleet_memory
        with patch.object(fleet_memory, "FLEET_BRIDGE_KEY", ""), \
                patch.object(fleet_memory, "QDRANT_API_KEY", "qdrant-secret"):
            for name, kwargs in self.DESKTOP_CALLS:
                res = getattr(fleet_memory, name)(**kwargs)
                self.assertEqual(res.get("status"), "error", name)
                self.assertIn("FLEET_BRIDGE_KEY", res.get("message", ""), name)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_delegate_flags_a_task_token_that_is_the_qdrant_key(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"task_id": "tsk_1", "status": "pending"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(fleet_memory, "FLEET_TASKS_URL", "http://127.0.0.1:8000"), \
                patch.object(fleet_memory, "QDRANT_API_KEY", "same"), \
                patch.object(fleet_memory, "FLEET_KEY", "same"):
            fused = fleet_memory.fleet_task_delegate(target_node="a", action="fleet_health_ping")
        with patch.object(fleet_memory, "FLEET_TASKS_URL", "http://127.0.0.1:8000"), \
                patch.object(fleet_memory, "QDRANT_API_KEY", "qdrant"), \
                patch.object(fleet_memory, "FLEET_KEY", "task"):
            separate = fleet_memory.fleet_task_delegate(target_node="a", action="fleet_health_ping")

        self.assertIn("key_warning", fused)
        self.assertNotIn("key_warning", separate)


class TestTaskKeyResolution(unittest.TestCase):

    def resolve(self, env, auth_file=None):
        import tempfile

        import fleet_memory
        with tempfile.TemporaryDirectory() as home:
            if auth_file is not None:
                with open(os.path.join(home, "auth.json"), "w", encoding="utf-8") as f:
                    f.write(auth_file)
            with patch.dict(os.environ, {"FLEET_HOME": home, **env}, clear=True), \
                    patch("os.path.expanduser", return_value=home):
                return fleet_memory._resolve_task_key()

    def test_fleet_key_wins_over_the_qdrant_key(self):
        self.assertEqual(self.resolve({"FLEET_KEY": "t", "FLEET_QDRANT_KEY": "q"}), ("t", "FLEET_KEY"))

    def test_auth_file_is_read(self):
        self.assertEqual(self.resolve({"FLEET_QDRANT_KEY": "q"}, '{"fleet_key": "f"}'),
                         ("f", "fleet_auth.json"))

    def test_unreadable_auth_file_is_skipped(self):
        self.assertEqual(self.resolve({"FLEET_QDRANT_KEY": "q"}, "not json"), ("q", "FLEET_QDRANT_KEY"))

    def test_qdrant_key_is_the_last_resort(self):
        self.assertEqual(self.resolve({"FLEET_CLUSTER_SECRET": "c", "FLEET_QDRANT_KEY": "q"}),
                         ("c", "FLEET_CLUSTER_SECRET"))
        self.assertEqual(self.resolve({}), ("", ""))
