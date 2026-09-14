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
        os.environ["FLEET_HARD_DOMAIN"] = "all"
        os.environ["FLEET_KEY"] = "test_key"
        os.environ["FLEET_TASKS_URL"] = "http://127.0.0.1:8000"

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

        res = fleet_memory.fleet_task_delegate(target_node="chester", action="telegram_notify", params={"message": "hi"})
        self.assertEqual(res.get("status"), "accepted")
        self.assertEqual(res.get("task_id"), "tsk_123")

    @patch("urllib.request.urlopen")
    def test_fleet_task_status(self, mock_urlopen):
        import fleet_memory
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"task_id": "tsk_123", "status": "completed", "result": {"output": "done"}}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = fleet_memory.fleet_task_status(task_id="tsk_123", verify_receipt=False)
        self.assertEqual(res.get("status"), "completed")

    @patch("fleet_memory.get_client")
    @patch("fleet_memory.get_embedder")
    def test_fleet_synapse_search(self, mock_get_embedder, mock_client):
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
    def test_fleet_synapse_store(self, mock_get_embedder, mock_client):
        import fleet_memory
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.1] * 384]
        mock_get_embedder.return_value = mock_embedder
        mock_client.return_value.upsert.return_value = MagicMock()

        res = fleet_memory.fleet_memory_store(text="New architectural decision")
        self.assertEqual(res.get("status"), "success")


if __name__ == "__main__":
    unittest.main()
