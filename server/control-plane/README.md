# Fleet Control Plane

A small, self-hosted task queue for coordinating work between machines you own.
Submit a task from any node, a worker executes it, and the completion receipt is
signed with Ed25519 so any peer can verify it independently.

Runs on a **single laptop with no server**, or across several machines. Nothing
here requires a VPS, a domain, or a TLS certificate.

---

## What it actually does

1. A caller `POST`s a task to `/api/fleet/tasks` with a bearer token.
2. The task is written to SQLite (WAL) and the local worker is woken.
3. The worker claims it, performs one **allowlisted** action, and writes an
   outbox row before delivering anything externally.
4. The receipt is signed; the caller fetches `GET /api/fleet/tasks/{id}` and
   verifies the signature against the published public key.

Only three actions can ever run. Remote code execution is not possible by design.

| Action | Effect |
| --- | --- |
| `fleet_health_ping` | Returns load, pid, and timestamp for the target node |
| `telegram_notify` | Sends a message and/or photo via a Telegram bot (optional) |
| `gpu_batch` | Reserved for a GPU worker on that node |

---

## Quick start (one machine, no VPS)

```bash
pip install fastapi uvicorn pydantic cryptography

cd server/control-plane
python setup_fleet.py --init          # writes ~/.fleet/.env, keys, database
python app.py                         # terminal 1 - API on 127.0.0.1:8088
python worker.py                      # terminal 2 - worker
```

Delegate something:

```bash
python client_delegate.py --action fleet_health_ping
```

You should see `status: completed` and `receipt signature: VERIFIED`.

### Adding Telegram (optional)

```bash
python setup_fleet.py --init --force \
  --telegram-token "123456:ABC..." --telegram-chat-id "123456789"

python client_delegate.py --message "hello from the fleet"
```

Without both Telegram values, notification tasks complete with
`notification_status: "skipped"` and a note explaining how to enable it —
they are never retried into a dead-letter pile.

### Adding a second machine

```bash
# on the second machine, same FLEET_HOME layout
python setup_fleet.py --init --node-id node-b --nodes local,node-b --port 8089
```

Each node submits tasks addressed to `target: "node-b"`, and every node runs its
own worker that only claims tasks addressed to itself.

---

## Configuration

Everything lives in `$FLEET_HOME/.env` (default `~/.fleet/.env`, mode 0600).
Process environment always wins over the file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FLEET_HOME` | `~/.fleet` | All state: config, keys, database |
| `FLEET_NODE_ID` | `local` | Name of this machine |
| `FLEET_NODES` | `$FLEET_NODE_ID` | Comma-separated roster of valid targets |
| `FLEET_KEY_<NODE>` | generated | Bearer token accepted for that node |
| `FLEET_HOST` / `FLEET_PORT` | `127.0.0.1` / `8088` | Bind address |
| `FLEET_KEY_ID` | `<node>-fleet-1` | Receipt key identifier |
| `TELEGRAM_BOT_TOKEN` | — | Optional |
| `TELEGRAM_CHAT_ID` | — | Optional; required for delivery |

`$FLEET_HOME` holds: `.env`, `tasks.db` (+WAL), `fleet_ed25519.key`,
`fleet_keys.json`.

### Reaching it from another machine

Set `FLEET_HOST=0.0.0.0` only behind a TLS reverse proxy (Caddy, nginx, or a
tunnel). On the client, point at it with `--url https://your.host` or put
`{"fleet_endpoint": "...", "fleet_key": "..."}` in `~/.hermes/fleet_auth.json`.

---

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | no | Status, roster, queue depth |
| `GET` | `/` | no | Read-only task board |
| `GET` | `/.well-known/fleet-keys.json` | no | Public verification keys |
| `GET` | `/api/fleet/tasks` | bearer | Recent tasks for the caller's node |
| `POST` | `/api/fleet/tasks` | bearer | Submit (`202 Accepted`) |
| `GET` | `/api/fleet/tasks/{id}` | bearer | Status, result, signature |
| `GET` | `/api/fleet/tasks/internal/wait-task` | bearer | Long-poll wake for the local worker |

---

## Verifying a receipt yourself

```python
from verify import fetch_jwks, verify_receipt
record = {"task_id": "...", "completed_at": 1789032616.08,
          "result": {...}, "ed25519_signature": "...", "kid": "..."}
print(verify_receipt(record, fetch_jwks("http://127.0.0.1:8088")))
```

The signed byte string is
`json.dumps({"completed_at": round(t,3), "result": r, "task_id": id}, sort_keys=True, separators=(",",":"))`.
Keep it byte-identical or existing receipts stop verifying.

---

## Tests

```bash
python tests/smoke_test.py
```

Covers bootstrap, auth rejection, schema validation, idempotent replay,
execution with Telegram off and on, signature verification, and tamper
detection — against a throwaway `FLEET_HOME`.

---

## Operations

`systemd/fleet-control-plane.service` and `systemd/fleet-worker.service` are
templates. Set `User=` and the paths for your host; CPU pinning is present but
commented out, since it only helps on boxes that also run latency-sensitive
inference. See `RUNBOOK.md`.

---

## Security notes

* Bearer tokens and the signing key live in `$FLEET_HOME`, never in source.
* The signing key is generated on first run and written `0600`.
* Bind to loopback unless you have a TLS terminator in front.
* `/` and `/healthz` are unauthenticated and read-only; do not expose them
  publicly without a proxy-level allowlist if that matters to you.
* Rotate tokens with `python setup_fleet.py --init --force`.
