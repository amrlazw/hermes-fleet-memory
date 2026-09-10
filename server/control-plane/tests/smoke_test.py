"""End-to-end smoke test for the packaged control plane.

Runs against a throwaway FLEET_HOME so it never touches real state:

    python tests/smoke_test.py

Covers: bootstrap -> auth -> submit -> idempotency -> worker execution
        (Telegram off and on) -> Ed25519 receipt verification.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
CP = HERE.parent
sys.path.insert(0, str(CP))

TMP_HOME = Path(tempfile.mkdtemp(prefix="fleet-smoke-"))
os.environ["FLEET_HOME"] = str(TMP_HOME)
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)

PASS, FAIL = [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def main() -> int:
    import config

    print(f"FLEET_HOME = {TMP_HOME}\n")

    # ---------------------------------------------------------- 1. bootstrap
    print("[1] Bootstrap (setup_fleet.py --init)")
    import setup_fleet
    rc = setup_fleet.main(["--init", "--node-id", "alpha", "--nodes", "alpha,beta"])
    config._cached = None
    cfg = config.get_config()
    check("setup exits 0", rc == 0, f"rc={rc}")
    check(".env written", cfg.env_file.is_file())
    check("ed25519 private key created", cfg.key_path.is_file())
    check("JWKS published", cfg.jwks_path.is_file())
    check("database created", cfg.db_path.is_file())
    check("node roster parsed", cfg.nodes == ["alpha", "beta"], str(cfg.nodes))
    check("two node tokens generated", len(cfg.node_keys) == 2, str(len(cfg.node_keys)))
    check("telegram disabled by default", cfg.telegram_enabled is False)

    jwks = json.loads(cfg.jwks_path.read_text())
    check("JWKS has Ed25519 key", jwks["keys"][0]["crv"] == "Ed25519")

    # ------------------------------------------------------- 2. API + auth
    print("\n[2] API surface and bearer auth")
    from fastapi.testclient import TestClient
    import app as app_module

    client = TestClient(app_module.app)
    alpha_token = next(t for t, n in cfg.node_keys.items() if n == "alpha")

    r = client.get("/healthz")
    check("healthz 200", r.status_code == 200, str(r.status_code))
    check("healthz reports telegram off", r.json()["telegram_configured"] is False)

    r = client.get("/.well-known/fleet-keys.json")
    check("public keys endpoint 200", r.status_code == 200)

    r = client.get("/api/fleet/tasks")
    check("unauthenticated request rejected", r.status_code in (401, 503), str(r.status_code))

    r = client.get("/api/fleet/tasks", headers={"Authorization": "Bearer wrong-token"})
    check("bad token rejected", r.status_code == 401, str(r.status_code))

    # ------------------------------------------------------------- 3. submit
    print("\n[3] Task submission and validation")
    auth = {"Authorization": f"Bearer {alpha_token}"}
    payload = {
        "target": "alpha",
        "action": "fleet_health_ping",
        "priority": "normal",
        "params": {},
        "idempotency_key": "smoke-health-0001",
    }
    r = client.post("/api/fleet/tasks", json=payload, headers=auth)
    check("submit returns 202", r.status_code == 202, str(r.status_code))
    task_id = r.json()["task_id"]

    r = client.post("/api/fleet/tasks", json=payload, headers=auth)
    check("idempotent replay deduped",
          r.json().get("idempotent_replay") is True and r.json()["task_id"] == task_id)

    r = client.post("/api/fleet/tasks",
                    json={**payload, "idempotency_key": "smoke-bad-node-1", "target": "ghost"},
                    headers=auth)
    check("unknown node rejected (422)", r.status_code == 422, str(r.status_code))

    r = client.post("/api/fleet/tasks",
                    json={**payload, "idempotency_key": "smoke-bad-action-1", "action": "rm_rf"},
                    headers=auth)
    check("non-allowlisted action rejected (422)", r.status_code == 422, str(r.status_code))

    r = client.post("/api/fleet/tasks",
                    json={**payload, "idempotency_key": "smoke-bad-photo-1",
                          "action": "telegram_notify", "params": {}},
                    headers=auth)
    check("empty notification rejected (422)", r.status_code == 422, str(r.status_code))

    # ------------------------------------------- 4. worker, telegram disabled
    print("\n[4] Worker execution with Telegram disabled")
    import worker

    conn = worker.sqlite3.connect(str(cfg.db_path))
    conn.row_factory = worker.sqlite3.Row
    worker.run_cycle(conn)
    conn.close()

    r = client.get(f"/api/fleet/tasks/{task_id}", headers=auth)
    body = r.json()
    check("task completed", body["status"] == "completed", body["status"])
    check("health result present", body["result"]["status"] == "online")
    check("signature produced", bool(body["ed25519_signature"]))
    check("key id recorded", body["kid"] == cfg.key_id)

    from verify import verify_receipt
    check("receipt verifies against published JWKS", verify_receipt(body, jwks) is True)

    # notification task with telegram off -> skipped, not dead-lettered
    r = client.post("/api/fleet/tasks",
                    json={"target": "alpha", "action": "telegram_notify", "priority": "normal",
                          "params": {"message": "hello"}, "idempotency_key": "smoke-notify-0001"},
                    headers=auth)
    notify_id = r.json()["task_id"]
    conn = worker.sqlite3.connect(str(cfg.db_path))
    conn.row_factory = worker.sqlite3.Row
    worker.run_cycle(conn)
    conn.close()

    body = client.get(f"/api/fleet/tasks/{notify_id}", headers=auth).json()
    check("notification task did not dead-letter", body["status"] == "completed", body["status"])
    check("notification marked skipped",
          body["result"]["notification_status"] == "skipped",
          str(body["result"].get("notification_status")))
    check("skip reason surfaced to caller", "note" in body["result"])

    # ------------------------------------------ 5. worker, telegram simulated
    print("\n[5] Worker execution with Telegram simulated")
    sent = []

    def fake_post(method, payload, timeout=15):
        sent.append((method, payload))
        return {"ok": True, "result": {"message_id": 4242}}

    worker.telegram_post = fake_post
    worker._cfg.__class__.telegram_enabled = property(lambda self: True)
    worker._cfg.__class__.telegram_chat_id = property(lambda self: "999888")
    worker._cfg.__class__.telegram_token = property(lambda self: "fake-token")

    r = client.post("/api/fleet/tasks",
                    json={"target": "alpha", "action": "telegram_notify", "priority": "normal",
                          "params": {"message": "Gear 5", "photo_url": "https://example.com/g5.jpg"},
                          "idempotency_key": "smoke-photo-0001"},
                    headers=auth)
    photo_id = r.json()["task_id"]
    conn = worker.sqlite3.connect(str(cfg.db_path))
    conn.row_factory = worker.sqlite3.Row
    worker.run_cycle(conn)
    conn.close()

    body = client.get(f"/api/fleet/tasks/{photo_id}", headers=auth).json()
    check("photo task completed", body["status"] == "completed", body["status"])
    check("sendPhoto used for photo_url",
          sent and sent[-1][0] == "sendPhoto", str(sent[-1][0] if sent else None))
    check("caption carried through", sent[-1][1].get("caption") == "Gear 5")
    check("telegram message id recorded",
          body["result"]["notification_status"] == "delivered"
          and body["result"]["receipt"]["message_id"] == 4242)

    # --------------------------------------------------------- 6. tampering
    print("\n[6] Signature tamper detection")
    forged = dict(body)
    forged["result"] = {"outbox_id": "x", "channel": "telegram_photo",
                        "notification_status": "delivered", "receipt": {"message_id": 1}}
    check("forged result fails verification", verify_receipt(forged, jwks) is False)

    # ------------------------------------------------------------ 7. long-poll
    print("\n[7] Long-poll wake endpoint")
    r = client.get("/api/fleet/tasks/internal/wait-task", headers=auth)
    check("wait-task responds", r.status_code == 200, str(r.status_code))

    print(f"\n{'=' * 56}\n{dict(passed=len(PASS), failed=len(FAIL))}")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:
        traceback.print_exc()
        rc = 1
    finally:
        shutil.rmtree(TMP_HOME, ignore_errors=True)
    sys.exit(rc)
