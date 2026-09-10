"""Execution worker — claims queued tasks, performs allowlisted actions,
records Ed25519-signed receipts through a transactional outbox.

Runs on the node named by FLEET_NODE_ID. Degrades gracefully: with no Telegram
credentials configured, notification tasks complete as 'skipped' rather than
retrying into a dead-letter pile.

    python worker.py
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request

from config import get_config
from init_db import init_db
from keys import ensure_keys
from verify import canonical_receipt_bytes

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [%(levelname)s] [fleet-worker] %(message)s")
log = logging.getLogger("fleet-worker")

_cfg = get_config()
DB_PATH = str(_cfg.db_path)
NODE_ID = _cfg.node_id
API_INTERNAL_URL = f"http://{_cfg.host}:{_cfg.port}/api/fleet/tasks/internal/wait-task"
KEY_PATH = str(_cfg.key_path)
KID = _cfg.key_id

if not os.path.exists(KEY_PATH):
    ensure_keys(_cfg)

PRIVATE_KEY, PUBLIC_KEY, _ = ensure_keys(_cfg)


def node_key() -> str:
    """This node's own bearer token, used for the loopback long-poll."""
    for token, node in _cfg.node_keys.items():
        if node == NODE_ID:
            return token
    return ""


# --------------------------------------------------------------------- signing
def sign_receipt(task_id: str, completed_at: float, result: dict):
    signature = PRIVATE_KEY.sign(canonical_receipt_bytes(task_id, completed_at, result))
    return signature.hex(), KID


# ---------------------------------------------------------------------- outbox
def telegram_post(method: str, payload: dict, timeout: int = 15) -> dict:
    url = f"https://api.telegram.org/bot{_cfg.telegram_token}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def process_outbox(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now = time.time()

    if not _cfg.telegram_enabled:
        cur.execute("""UPDATE notification_outbox
                       SET status = 'skipped', error = 'telegram not configured'
                       WHERE status = 'pending'""")
        conn.commit()
        return

    rows = cur.execute(
        """SELECT * FROM notification_outbox
           WHERE status = 'pending' AND next_attempt_at <= ?
           ORDER BY created_at ASC LIMIT 5""",
        (now,),
    ).fetchall()

    for item in rows:
        outbox_id = item["outbox_id"]
        retries = item["retry_count"]
        max_retries = item["max_retries"]

        try:
            if item["channel"] == "telegram_photo":
                blob = json.loads(item["content"])
                method, payload = "sendPhoto", {
                    "chat_id": item["destination"],
                    "photo": blob.get("photo_url"),
                    "caption": blob.get("caption", ""),
                }
            else:
                method, payload = "sendMessage", {
                    "chat_id": item["destination"],
                    "text": item["content"],
                }

            data = telegram_post(method, payload)
            message_id = data.get("result", {}).get("message_id")

            cur.execute(
                """UPDATE notification_outbox
                   SET status='delivered', delivered_at=?, receipt=?, error=NULL
                   WHERE outbox_id=?""",
                (time.time(), json.dumps({"message_id": message_id}), outbox_id),
            )
            conn.commit()
            log.info("Outbox %s delivered (telegram message_id=%s)", outbox_id, message_id)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code == 429:
                delay = int(exc.headers.get("Retry-After", 5))
                cur.execute("UPDATE notification_outbox SET next_attempt_at=? WHERE outbox_id=?",
                            (time.time() + delay, outbox_id))
                conn.commit()
                log.warning("Rate limited; retrying %s in %ss", outbox_id, delay)
                continue
            _fail_outbox(cur, conn, outbox_id, retries, max_retries, f"HTTP {exc.code}: {body[:200]}")

        except Exception as exc:  # noqa: BLE001 - outbox must never crash the loop
            _fail_outbox(cur, conn, outbox_id, retries, max_retries, str(exc))


def _fail_outbox(cur, conn, outbox_id, retries, max_retries, message):
    attempt = retries + 1
    if attempt >= max_retries:
        cur.execute("""UPDATE notification_outbox
                       SET status='dead_letter', retry_count=?, error=?
                       WHERE outbox_id=?""", (attempt, message, outbox_id))
        log.error("Outbox %s dead-lettered: %s", outbox_id, message)
    else:
        backoff = 2 ** attempt
        cur.execute("""UPDATE notification_outbox
                       SET status='pending', retry_count=?, next_attempt_at=?, error=?
                       WHERE outbox_id=?""",
                    (attempt, time.time() + backoff, message, outbox_id))
        log.warning("Outbox %s failed (%s); retry in %ss", outbox_id, message, backoff)
    conn.commit()


# --------------------------------------------------------------- worker cycle
def run_cycle(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now = time.time()

    # Reclaim tasks whose lease expired.
    cur.execute("""UPDATE fleet_tasks
                   SET status='pending', lease_until=NULL, retry_count=retry_count+1,
                       next_attempt_at=?
                   WHERE status='running' AND lease_until < ? AND retry_count < max_retries""",
                (now + 2, now))
    cur.execute("""UPDATE fleet_tasks
                   SET status='dead_letter', error='lease expired, retries exhausted'
                   WHERE status='running' AND lease_until < ? AND retry_count >= max_retries""",
                (now,))
    conn.commit()

    cur.execute("BEGIN IMMEDIATE")
    task = cur.execute(
        f"""SELECT * FROM fleet_tasks
            WHERE target = ? AND status = 'pending' AND next_attempt_at <= ?
            ORDER BY {PRIORITY_ORDER_SQL}, created_at ASC LIMIT 1""",
        (NODE_ID, now),
    ).fetchone()

    if not task:
        conn.commit()
        process_outbox(conn)
        return

    task_id = task["task_id"]
    action = task["action"]
    params = json.loads(task["params"] or "{}")
    lease_until = now + task["lease_ttl"]

    cur.execute("""UPDATE fleet_tasks
                   SET status='running', lease_until=?, heartbeat_at=?, worker_id=?
                   WHERE task_id=?""", (lease_until, now, NODE_ID, task_id))
    conn.commit()
    log.info("Claimed %s action=%s caller=%s", task_id, action, task["caller"])

    try:
        completed_at = time.time()

        if action == "telegram_notify":
            message = params.get("message", "")
            photo_url = params.get("photo_url")
            outbox_id = f"ob_{task_id[:12]}_{int(completed_at)}"

            if photo_url:
                channel = "telegram_photo"
                content = json.dumps({"photo_url": photo_url, "caption": message})
            else:
                channel = "telegram"
                content = message

            destination = _cfg.telegram_chat_id or "(unset)"
            cur.execute("""INSERT INTO notification_outbox (
                               outbox_id, task_id, channel, destination, content,
                               status, created_at, next_attempt_at)
                           VALUES (?,?,?,?,?,'pending',?,?)""",
                        (outbox_id, task_id, channel, destination, content,
                         completed_at, completed_at))
            conn.commit()
            process_outbox(conn)

            row = cur.execute("SELECT status, receipt, error FROM notification_outbox "
                              "WHERE outbox_id=?", (outbox_id,)).fetchone()
            result = {
                "outbox_id": outbox_id,
                "channel": channel,
                "notification_status": row["status"],
                "receipt": json.loads(row["receipt"]) if row["receipt"] else None,
            }
            if row["status"] == "skipped":
                result["note"] = ("Telegram is not configured; set TELEGRAM_BOT_TOKEN and "
                                  "TELEGRAM_CHAT_ID to enable delivery.")

        elif action == "fleet_health_ping":
            load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
            result = {"status": "online", "node": NODE_ID, "pid": os.getpid(),
                      "load": list(load), "time": completed_at}

        else:
            raise ValueError(f"unsupported action: {action}")

        signature, kid = sign_receipt(task_id, completed_at, result)
        cur.execute("""UPDATE fleet_tasks
                       SET status='completed', completed_at=?, result=?, ed25519_signature=?,
                           kid=?, error=NULL
                       WHERE task_id=?""",
                    (completed_at, json.dumps(result), signature, kid, task_id))
        conn.commit()
        log.info("Task %s completed (sig %s...)", task_id, signature[:16])

    except Exception as exc:  # noqa: BLE001
        attempt = task["retry_count"] + 1
        if attempt >= task["max_retries"]:
            new_status, next_try = "dead_letter", time.time() + 999999
            log.error("Task %s dead-lettered: %s", task_id, exc)
        else:
            new_status, next_try = "pending", time.time() + 2 ** attempt
            log.warning("Task %s failed (%s); retry in %ss", task_id, exc, 2 ** attempt)

        cur.execute("""UPDATE fleet_tasks
                       SET status=?, retry_count=?, next_attempt_at=?, error=?
                       WHERE task_id=?""",
                    (new_status, attempt, next_try, str(exc), task_id))
        conn.commit()


PRIORITY_ORDER_SQL = ("CASE priority WHEN 'critical' THEN 1 "
                      "WHEN 'normal' THEN 2 ELSE 3 END")


def run_worker() -> None:
    init_db(verbose=False)
    log.info("Worker up: node=%s home=%s", NODE_ID, _cfg.home)
    if not _cfg.telegram_enabled:
        log.warning("Telegram not configured - notification tasks will be marked 'skipped'.")
    if not _cfg.node_keys:
        log.warning("No FLEET_KEY_<NODE> configured - loopback long-poll auth will fail. "
                    "Run setup_fleet.py --init.")

    token = node_key()
    while True:
        try:
            if token:
                try:
                    req = urllib.request.Request(
                        API_INTERNAL_URL,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    urllib.request.urlopen(req, timeout=25).read()
                except Exception:
                    pass  # API restarting or window closed; fall through to DB poll

            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000;")
            try:
                run_cycle(conn)
            finally:
                conn.close()

        except Exception as exc:  # noqa: BLE001 - the loop must survive anything
            log.error("Loop error: %s", exc)
            time.sleep(2)


if __name__ == "__main__":
    run_worker()
