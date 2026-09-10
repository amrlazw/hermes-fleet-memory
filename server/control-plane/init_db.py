"""Bootstrap the SQLite WAL task database under FLEET_HOME.

Idempotent: safe to run repeatedly. Creates the task queue, the transactional
notification outbox, and the receipt index.

    python init_db.py
"""
from __future__ import annotations

import sqlite3

from config import get_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS fleet_tasks (
    task_id            TEXT PRIMARY KEY,
    target             TEXT NOT NULL,
    action             TEXT NOT NULL,
    priority           TEXT NOT NULL DEFAULT 'normal',
    params             TEXT NOT NULL,
    idempotency_key    TEXT NOT NULL UNIQUE,
    status             TEXT NOT NULL DEFAULT 'pending',
    caller             TEXT,
    created_at         REAL NOT NULL,
    lease_ttl          INTEGER NOT NULL DEFAULT 300,
    lease_until        REAL,
    heartbeat_at       REAL,
    worker_id          TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    max_retries        INTEGER NOT NULL DEFAULT 5,
    next_attempt_at    REAL NOT NULL DEFAULT 0,
    completed_at       REAL,
    result             TEXT,
    ed25519_signature  TEXT,
    kid                TEXT,
    error              TEXT
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    outbox_id       TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    destination     TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 5,
    next_attempt_at REAL NOT NULL,
    created_at      REAL NOT NULL,
    delivered_at    REAL,
    receipt         TEXT,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_target_status ON fleet_tasks (target, status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_tasks_idempotency   ON fleet_tasks (idempotency_key);
CREATE INDEX IF NOT EXISTS idx_outbox_status       ON notification_outbox (status, next_attempt_at);
"""


def init_db(verbose: bool = True) -> str:
    cfg = get_config()
    conn = sqlite3.connect(str(cfg.db_path), timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

    if verbose:
        print(f"[fleet] database ready: {cfg.db_path}")
    return str(cfg.db_path)


if __name__ == "__main__":
    init_db()
