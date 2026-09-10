"""Fleet Control Plane API + minimal task board.

Intentionally small: this ships only what an operator needs — the task queue
API, the public key endpoint, a health probe, and a read-only board. Personal
documents (RFCs, post-mortems, PDFs) are NOT part of this package.

    uvicorn app:app --host 127.0.0.1 --port 8088
"""
from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from config import get_config
from init_db import init_db
from keys import ensure_keys
import task_routes

_cfg = get_config()

init_db(verbose=False)
PRIVATE_KEY, PUBLIC_KEY, KEYS_GENERATED = ensure_keys(_cfg)

app = FastAPI(title="Fleet Control Plane", version="3.0.0")
app.include_router(task_routes.router)


@app.get("/.well-known/fleet-keys.json")
def fleet_keys():
    """Public verification keys. Safe to expose — public halves only."""
    return JSONResponse(json.loads(_cfg.jwks_path.read_text(encoding="utf-8")))


@app.get("/healthz")
def healthz():
    try:
        conn = sqlite3.connect(str(_cfg.db_path), timeout=5)
        pending = conn.execute(
            "SELECT COUNT(*) FROM fleet_tasks WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
        db_ok = True
    except Exception:
        pending, db_ok = -1, False

    return {
        "status": "ok" if db_ok else "degraded",
        "node_id": _cfg.node_id,
        "key_id": _cfg.key_id,
        "nodes": _cfg.nodes,
        "telegram_configured": _cfg.telegram_enabled,
        "node_keys_configured": len(_cfg.node_keys),
        "pending_tasks": pending,
        "public_key_ready": PUBLIC_KEY is not None,
    }


@app.get("/", response_class=HTMLResponse)
def board():
    """Read-only task board. Not an admin console - no mutations here."""
    conn = sqlite3.connect(str(_cfg.db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT task_id, target, action, priority, status, created_at, completed_at, error "
        "FROM fleet_tasks ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    body = "".join(
        f"<tr><td>{r['task_id'][:8]}</td><td>{r['target']}</td><td>{r['action']}</td>"
        f"<td>{r['priority']}</td><td class='{r['status']}'>{r['status']}</td>"
        f"<td>{r['created_at']:.0f}</td><td>{(r['error'] or '')[:60]}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7'>No tasks yet.</td></tr>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Fleet Control Plane</title><style>
body{{background:#0e1116;color:#d7dde7;font:14px ui-monospace,monospace;margin:24px}}
h1{{font-size:16px;font-weight:600}} .meta{{color:#7d8797;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 10px;
border-bottom:1px solid #1e242e}} th{{color:#7d8797;font-weight:500}}
.completed{{color:#3fb950}}.pending{{color:#d29922}}.running{{color:#58a6ff}}
.dead_letter,.failed{{color:#f85149}}
</style></head><body>
<h1>Fleet Control Plane</h1>
<div class="meta">node={_cfg.node_id} &middot; key={_cfg.key_id} &middot;
nodes={', '.join(_cfg.nodes)} &middot; telegram={'on' if _cfg.telegram_enabled else 'off'}</div>
<table><thead><tr><th>id</th><th>target</th><th>action</th><th>prio</th><th>status</th>
<th>created</th><th>error</th></tr></thead><tbody>{body}</tbody></table>
</body></html>"""


def main() -> None:
    import uvicorn

    if KEYS_GENERATED:
        print(f"[fleet] generated new Ed25519 receipt key: {_cfg.key_path}")
    print(f"[fleet] control plane starting\n{_cfg.describe()}")
    uvicorn.run(app, host=_cfg.host, port=_cfg.port, log_level="info")


if __name__ == "__main__":
    main()
