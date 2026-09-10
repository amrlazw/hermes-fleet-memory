"""Canonical receipt form and Ed25519 verification.

The canonical byte string is the contract between worker (signer) and every
verifier. Do not change it without versioning, or previously issued receipts
stop verifying:

    json.dumps({"completed_at": round(t, 3), "result": {...}, "task_id": "..."},
               sort_keys=True, separators=(",", ":"))
"""
from __future__ import annotations

import json
import urllib.request


def canonical_receipt_bytes(task_id: str, completed_at: float, result: dict) -> bytes:
    payload = {
        "completed_at": round(completed_at, 3),
        "result": result,
        "task_id": task_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fetch_jwks(base_url: str, timeout: int = 10) -> dict:
    url = base_url.rstrip("/") + "/.well-known/fleet-keys.json"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_receipt(record: dict, jwks: dict) -> bool:
    """Verify a task record's Ed25519 signature against a JWKS document."""
    from keys import load_public_key_from_jwks

    signature = record.get("ed25519_signature")
    completed_at = record.get("completed_at")
    result = record.get("result")
    task_id = record.get("task_id")

    if not signature or completed_at is None or result is None:
        return False

    if isinstance(result, str):
        result = json.loads(result)

    try:
        public = load_public_key_from_jwks(jwks, kid=record.get("kid"))
        public.verify(bytes.fromhex(signature),
                      canonical_receipt_bytes(task_id, completed_at, result))
        return True
    except Exception:
        return False
