"""Receipt verification against the shipped control plane's key format, and retry-safe delegation."""
import base64
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client")))

import fleet_memory  # noqa: E402

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
except ImportError:  # pragma: no cover
    ed25519 = None

HUB = "http://127.0.0.1:8088"


def _response(body):
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode("utf-8")
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    return ctx


class TestReceiptVerification(unittest.TestCase):

    def setUp(self):
        if not getattr(fleet_memory, "HAS_MCP", False) or ed25519 is None:
            self.skipTest("FastMCP or cryptography is not installed")
        for name, value in (("FLEET_TASKS_URL", HUB), ("FLEET_KEY", "task-token")):
            p = patch.object(fleet_memory, name, value)
            p.start()
            self.addCleanup(p.stop)

        self.key = ed25519.Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.x_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        self.x_hex = raw.hex()

        completed_at = time.time()
        result = {"status": "online"}
        canonical = json.dumps({"completed_at": round(completed_at, 3), "result": result, "task_id": "t1"},
                               sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.task = {"task_id": "t1", "status": "completed", "result": result, "completed_at": completed_at,
                     "kid": "hub-fleet-1", "ed25519_signature": self.key.sign(canonical).hex()}

    def status(self, jwks, task=None, env=None):
        def fake_urlopen(req, timeout=None):
            url = req if isinstance(req, str) else req.full_url
            return _response(jwks if url.endswith("fleet-keys.json") else (task or self.task))

        env = env or {}
        with patch("urllib.request.urlopen", side_effect=fake_urlopen) as urlopen, \
                patch.dict(os.environ, env):
            if "FLEET_RECEIPT_JWKS" not in env:
                os.environ.pop("FLEET_RECEIPT_JWKS", None)
            res = fleet_memory.fleet_task_status(task_id="t1")
        return res, urlopen

    def jwks(self, x, kid="hub-fleet-1"):
        return {"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": kid, "x": x}]}

    def test_verifies_the_base64url_key_the_control_plane_publishes(self):
        res, _ = self.status(self.jwks(self.x_b64))
        self.assertTrue(res["receipt_verified"], res.get("verification_error"))
        self.assertEqual(res["receipt_key_source"], "fetched_from_hub")

    def test_still_verifies_legacy_hex_keys(self):
        res, _ = self.status(self.jwks(self.x_hex))
        self.assertTrue(res["receipt_verified"], res.get("verification_error"))

    def test_selects_the_key_by_kid(self):
        other = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        jwks = {"keys": [self.jwks(other, kid="old-key")["keys"][0], self.jwks(self.x_b64)["keys"][0]]}
        res, _ = self.status(jwks)
        self.assertTrue(res["receipt_verified"], res.get("verification_error"))

    def test_unknown_kid_fails_with_a_reason(self):
        res, _ = self.status(self.jwks(self.x_b64, kid="someone-else"))
        self.assertFalse(res["receipt_verified"])
        self.assertIn("hub-fleet-1", res["verification_error"])

    def test_tampered_result_fails(self):
        forged = dict(self.task, result={"status": "pwned"})
        res, _ = self.status(self.jwks(self.x_b64), task=forged)
        self.assertFalse(res["receipt_verified"])

    def test_pinned_keys_are_used_and_the_hub_is_not_asked(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(self.jwks(self.x_b64), f)
        self.addCleanup(os.unlink, f.name)
        attacker = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

        res, urlopen = self.status(self.jwks(attacker), env={"FLEET_RECEIPT_JWKS": f.name})

        self.assertTrue(res["receipt_verified"], res.get("verification_error"))
        self.assertEqual(res["receipt_key_source"], "pinned")
        fetched = [c.args[0] for c in urlopen.call_args_list if isinstance(c.args[0], str)]
        self.assertEqual(fetched, [])


class TestDelegateIdempotency(unittest.TestCase):

    def setUp(self):
        if not getattr(fleet_memory, "HAS_MCP", False):
            self.skipTest("FastMCP is not installed")
        for name, value in (("FLEET_TASKS_URL", HUB), ("FLEET_KEY", "task-token")):
            p = patch.object(fleet_memory, name, value)
            p.start()
            self.addCleanup(p.stop)

    def sent_keys(self, *calls):
        with patch("urllib.request.urlopen", return_value=_response({"task_id": "t1", "status": "pending"})) as u:
            results = [fleet_memory.fleet_task_delegate(target_node="a", action="fleet_health_ping", **kw)
                       for kw in calls]
        sent = [json.loads(c.args[0].data)["idempotency_key"] for c in u.call_args_list]
        return sent, results

    def test_caller_key_is_sent_so_retries_dedupe(self):
        sent, results = self.sent_keys({"idempotency_key": "retry-me-123"}, {"idempotency_key": "retry-me-123"})
        self.assertEqual(sent, ["retry-me-123", "retry-me-123"])
        self.assertEqual(results[0]["idempotency_key"], "retry-me-123")

    def test_default_keys_are_unique_even_within_a_millisecond(self):
        sent, _ = self.sent_keys({}, {})
        self.assertNotEqual(sent[0], sent[1])


if __name__ == "__main__":
    unittest.main()
