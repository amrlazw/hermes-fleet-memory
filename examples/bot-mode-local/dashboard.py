#!/usr/bin/env python3
"""Fleet office: watch the sandboxed agents from run_demo.py and give them tasks.

    python examples/bot-mode-local/run_demo.py ...        # start the agents first
    python examples/bot-mode-local/dashboard.py           # then open http://127.0.0.1:8130

Everything on the page comes from the agents' own session databases, read-only.
A task is delivered with `hermes peer dm`, from an "operator" Hermes home that
holds no model and runs no gateway. The server binds 127.0.0.1 only, and task
submissions need this run's token and the dashboard's own Origin, so another
website open in the same browser cannot send your agents work.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import run_demo

HERE = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(24)
OPERATOR = "Amirul"
MAX_TASK_CHARS = 2000
WORKING_WINDOW = 300  # seconds: an unanswered turn older than this is treated as stalled, not working

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


# --------------------------------------------------------------------- reading the agents
def _db(home: str) -> sqlite3.Connection | None:
    path = Path(home) / "state.db"
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    return con


def _peer_name(target: str, names: list[str]) -> str:
    """message_agent targets look like 'winston', '@winston' or 'winston/researcher'."""
    t = target.lower().lstrip("@")
    for name in names:
        if t == name or t.startswith(name + "/") or t.startswith(name + "@"):
            return name
    return t


_FROM = re.compile(r"^Message from (?:🤖 )?(.+?) \(@[\w-]+\):\s*", re.S)


def agent_events(name: str, home: str, names: list[str]) -> tuple[list[dict], dict]:
    """Feed events and a status summary for one agent, straight from its state.db."""
    events, last_open, last_ts = [], None, 0.0
    con = _db(home)
    if con is None:
        return events, {"last_ts": 0, "open_since": None}
    try:
        rows = con.execute(
            "SELECT id, role, content, tool_calls, timestamp FROM messages ORDER BY timestamp, id").fetchall()
    finally:
        con.close()

    for row in rows:
        ts, role, content = row["timestamp"] or 0, row["role"], (row["content"] or "").strip()
        base = {"ts": ts, "agent": name}
        if role == "user":
            if content.startswith("[IMPORTANT: Background process"):
                continue  # delivery bookkeeping, not conversation
            last_open, last_ts = ts, ts
            if content.startswith("Message from 🤖"):
                continue  # already shown from the sender's side, as its message_agent call
            if content.startswith(f"Message from {OPERATOR} (operator"):
                text = content.split(":", 1)[1].strip() if ":" in content else content
                events.append({**base, "id": f"{name}:{row['id']}", "kind": "task",
                               "from": "you", "to": name, "text": text})
                continue
            match = _FROM.match(content)
            # No attribution header means it was typed into this agent's own console.
            sender = match.group(1).lower() if match else "you"
            events.append({**base, "id": f"{name}:{row['id']}", "kind": "message",
                           "from": sender, "to": name, "text": content[match.end():] if match else content})
        elif role == "assistant":
            last_ts = ts
            calls = []
            if row["tool_calls"]:
                try:
                    calls = json.loads(row["tool_calls"]) or []
                except ValueError:
                    calls = []
            for i, call in enumerate(calls):
                fn = (call or {}).get("function") or {}
                if fn.get("name") != "message_agent":
                    continue
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                events.append({**base, "id": f"{name}:{row['id']}:{i}", "kind": "message",
                               "from": name, "to": _peer_name(str(args.get("target", "")), names),
                               "text": str(args.get("message", ""))})
            if content:
                events.append({**base, "id": f"{name}:{row['id']}", "kind": "reply",
                               "from": name, "to": None, "text": content})
                last_open = None
            elif calls:
                last_open = last_open or ts
    return events, {"last_ts": last_ts, "open_since": last_open}


def snapshot(state: dict) -> dict:
    nodes = state["nodes"]
    names = list(nodes)
    now = time.time()
    with _tasks_lock:
        tasks = sorted(_tasks.values(), key=lambda t: t["started"], reverse=True)[:20]
        pending = {t["agent"] for t in _tasks.values() if t["status"] == "sending"}

    agents, events = [], []
    for name, node in nodes.items():
        evs, summary = agent_events(name, node["home"], names)
        events.extend(evs)
        online = run_demo.port_open(node["port"])
        open_since = summary["open_since"]
        if not online:
            status = "offline"
        elif name in pending or (open_since and now - open_since < WORKING_WINDOW):
            status = "working"
        else:
            status = "idle"
        meta = run_demo.NODES.get(name, {})
        agents.append({
            "name": name, "title": meta.get("title", name.title()), "role": meta.get("role", ""),
            "status": status, "last_ts": summary["last_ts"] or None,
            "sent": sum(1 for e in evs if e["kind"] == "message" and e["from"] == name),
        })
    for agent in agents:
        agent["received"] = sum(1 for e in events if e["kind"] in ("message", "task") and e["to"] == agent["name"])
    events.sort(key=lambda e: (e["ts"], e["id"]))
    return {"now": now, "operator": OPERATOR, "agents": agents, "events": events[-200:], "tasks": tasks}


# --------------------------------------------------------------------- giving tasks
def operator_home(root: Path, state: dict) -> str:
    """A model-less Hermes home that only knows the agents as peers, for sending tasks."""
    home = root / "operator"
    marker = home / ".peers-registered"
    if not marker.exists():
        home.mkdir(parents=True, exist_ok=True)
        for name, node in state["nodes"].items():
            res = run_demo.run(str(home), "peer", "add", name,
                               "--url", f"http://127.0.0.1:{node['port']}", "--key", node["key"], timeout=60)
            if res.returncode != 0:
                raise SystemExit(f"could not register {name} as a peer: {(res.stderr or res.stdout).strip()}")
        marker.write_text("ok", encoding="utf-8")
    return str(home)


def deliver(task: dict, home: str) -> None:
    body = f"Message from {OPERATOR} (operator, human): {task['text']}"
    try:
        res = subprocess.run([run_demo.hermes(), "peer", "dm", "--json", task["agent"]], input=body,
                             env=run_demo.env_for(home), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=900)
        out = res.stdout.strip()
        try:
            data = json.loads(out)
            reply = data.get("reply") or data.get("text") or data.get("output") or out
        except ValueError:
            reply = out or res.stderr.strip()
        status = "done" if res.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        reply, status = "No answer within 15 minutes. The agent may still be working.", "failed"
    with _tasks_lock:
        task.update(status=status, reply=str(reply)[:4000], finished=time.time())


# --------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FleetOffice"
    state: dict = {}
    operator: str = ""
    origins: set = set()

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data) -> None:
        self._send(code, json.dumps(data).encode("utf-8"), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (HERE / "office.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(200, snapshot(self.state))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/task":
            return self._json(404, {"error": "not found"})
        origin = self.headers.get("Origin")
        if origin not in self.origins:
            return self._json(403, {"error": "cross-origin request refused"})
        if not secrets.compare_digest(self.headers.get("X-Dashboard-Token", ""), TOKEN):
            return self._json(403, {"error": "bad dashboard token"})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(415, {"error": "send JSON"})
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 16_000)
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})
        agent, text = str(data.get("agent", "")), str(data.get("text", "")).strip()
        if agent not in self.state["nodes"]:
            return self._json(400, {"error": f"unknown agent {agent!r}"})
        if not text or len(text) > MAX_TASK_CHARS:
            return self._json(400, {"error": f"task must be 1-{MAX_TASK_CHARS} characters"})
        task = {"id": uuid.uuid4().hex[:12], "agent": agent, "text": text, "status": "sending",
                "reply": None, "started": time.time(), "finished": None}
        with _tasks_lock:
            _tasks[task["id"]] = task
        threading.Thread(target=deliver, args=(task, self.operator), daemon=True).start()
        self._json(202, {"id": task["id"]})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=run_demo.DEFAULT_DIR, help="sandbox created by run_demo.py")
    ap.add_argument("--port", type=int, default=8130)
    args = ap.parse_args()
    root = args.dir.resolve()

    Handler.state = run_demo.load(root)
    Handler.operator = operator_home(root, Handler.state)
    Handler.origins = {f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Fleet office: http://127.0.0.1:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
