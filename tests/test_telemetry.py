"""The setup beacon is opt-in and never fires from the MCP server or --doctor."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client")))

import fleet_memory  # noqa: E402

import fleet_wizard  # noqa: E402


class TestTelemetryOptIn(unittest.TestCase):

    def beacon_threads(self, env, send):
        with patch.dict(os.environ, env, clear=True), patch("threading.Thread") as thread:
            send()
        return thread.call_count

    def test_client_beacon_is_off_by_default(self):
        self.assertEqual(self.beacon_threads({}, fleet_memory.send_anonymous_beacon), 0)

    def test_client_beacon_needs_explicit_opt_in(self):
        self.assertEqual(self.beacon_threads({"FLEET_TELEMETRY": "1"}, fleet_memory.send_anonymous_beacon), 1)

    def test_do_not_track_overrides_opt_in(self):
        env = {"FLEET_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
        self.assertEqual(self.beacon_threads(env, fleet_memory.send_anonymous_beacon), 0)

    def test_wizard_beacon_is_off_by_default(self):
        self.assertEqual(self.beacon_threads({}, lambda: fleet_wizard.send_setup_beacon("hub")), 0)
        self.assertEqual(
            self.beacon_threads({"FLEET_TELEMETRY": "1"}, lambda: fleet_wizard.send_setup_beacon("hub")), 1)

    def test_doctor_and_serve_never_send_even_when_opted_in(self):
        with patch.dict(os.environ, {"FLEET_TELEMETRY": "1"}), \
                patch.object(fleet_memory, "send_anonymous_beacon") as beacon, \
                patch.object(fleet_memory, "cmd_doctor", return_value=0), \
                patch.object(fleet_memory, "cmd_serve", return_value=0), \
                patch.object(fleet_memory, "cmd_init", return_value=0):
            fleet_memory.main(["--doctor"])
            fleet_memory.main(["--serve"])
            beacon.assert_not_called()
            fleet_memory.main(["--init"])
            beacon.assert_called_once()


if __name__ == "__main__":
    unittest.main()
