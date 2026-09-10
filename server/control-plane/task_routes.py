"""Fleet task API — durable queue, bearer auth, loopback long-poll wake.

Endpoints (router prefix /api/fleet/tasks):
    GET  ""                          recent tasks for the caller's node
    POST ""                          submit a task -> 202 Accepted
    GET  "/{task_id}"                status, result, signature
    GET  "/internal/wait-task"       long-poll wake signal for the local worker
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import ValidationError

from config import get_config
from init_db import init_db
from schema import TaskRecord, TaskStatus, TaskSubmission

router = APIRouter(prefix="/api/fleet/tasks", tags=["fleet-tasks"])

_cfg = get_config()
task_arrived = asyncio.Event()

PRIORITY_ORDER = "CASE priority WHEN 'critical' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END"


def _now() -> float:
    return time.time()


def get_db():
    """Fresh connection per request; WAL + busy_timeout make this concurrency-safe."""
    conn = sqlite3.connect(str(_cfg.db_path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    try:
        yield conn
    finally:
        conn.close()


def authenticate_node(authorization: str = Header(default="")) -> str:
    """Map a bearer token to a node name using FLEET_KEY_<NODE> configuration."""
    keys = _cfg.node_keys
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No node credentials configured. Run 'python setup_fleet.py --init' "
                f"or add FLEET_KEY_<NODE>=... to {_cfg.env_file}"
            ),
        )

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    for secret, node in keys.items():
        if secrets.compare_digest(token, secret):
            return node
    raise HTTPException(status_code=401, detail="Unauthorized fleet key")


def _row_to_dict(row: sqlite3.Row) -> dict:
    record = dict(row)
    for field in ("params", "result"):
        if isinstance(record.get(field), str):
            try:
                record[field] = json.loads(record[field])
            except (ValueError, TypeError):
                pass
    return record


@router.get("")
def list_tasks(limit: int = 30, node: str = Depends(authenticate_node),
               db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        f"""SELECT * FROM fleet_tasks WHERE target = ?
            ORDER BY {PRIORITY_ORDER}, created_at DESC LIMIT ?""",
        (node, max(1, min(limit, 200))),
    ).fetchall()
    return {"node": node, "count": len(rows), "tasks": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_task(submission: TaskSubmission, node: str = Depends(authenticate_node),
                db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute(
        "SELECT * FROM fleet_tasks WHERE idempotency_key = ?",
        (submission.idempotency_key,),
    ).fetchone()
    if existing:
        return {"status": "duplicate", "task_id": existing["task_id"],
                "task_status": existing["status"], "idempotent_replay": True}

    pending = db.execute(
        "SELECT COUNT(*) AS n FROM fleet_tasks WHERE status = 'pending'"
    ).fetchone()["n"]
    if pending >= _cfg.max_pending:
        raise HTTPException(status_code=429, detail="Queue saturated; retry later")

    record = TaskRecord(
        target=submission.target,
        action=submission.action,
        priority=submission.priority,
        params=submission.params,
        idempotency_key=submission.idempotency_key,
        lease_ttl=min(submission.ttl_seconds, 300),
    )

    try:
        db.execute(
            """INSERT INTO fleet_tasks (
                   task_id, target, action, priority, params, idempotency_key,
                   status, caller, created_at, lease_ttl, max_retries, next_attempt_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record.task_id, record.target, record.action.value, record.priority.value,
             json.dumps(record.params), record.idempotency_key, TaskStatus.PENDING.value,
             node, record.created_at, record.lease_ttl, record.max_retries, _now()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        row = db.execute("SELECT * FROM fleet_tasks WHERE idempotency_key = ?",
                         (submission.idempotency_key,)).fetchone()
        return {"status": "duplicate", "task_id": row["task_id"],
                "task_status": row["status"], "idempotent_replay": True}

    task_arrived.set()

    return {
        "status": "accepted",
        "task_id": record.task_id,
        "task_status": TaskStatus.PENDING.value,
        "target": record.target,
        "action": record.action.value,
        "message": (f"Queued for {record.target}. Poll GET /api/fleet/tasks/{record.task_id} "
                    "to verify the Ed25519 receipt."),
    }


@router.get("/internal/wait-task")
async def wait_task(node: str = Depends(authenticate_node)):
    """Blocks until a task arrives or the window closes. Loopback-only by default."""
    try:
        await asyncio.wait_for(task_arrived.wait(), timeout=20)
        task_arrived.clear()
        return {"status": "task_available"}
    except asyncio.TimeoutError:
        return {"status": "idle"}


@router.get("/{task_id}")
def get_task(task_id: str, node: str = Depends(authenticate_node),
             db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM fleet_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return _row_to_dict(row)


__all__ = ["router", "init_db"]
