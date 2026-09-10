# RUNBOOK - Fleet Control Plane

Operational procedures. Assumes `FLEET_HOME=~/.fleet` unless stated otherwise.

---

## 1. First-time setup

```bash
pip install fastapi uvicorn pydantic cryptography
cd server/control-plane
python setup_fleet.py --init
```

Creates `~/.fleet/` containing `.env` (0600), `fleet_ed25519.key`,
`fleet_keys.json`, `tasks.db`. Re-running is safe; `--force` rotates secrets.

Verify before trusting it:

```bash
python -c "import json,os;print(open(os.path.expanduser('~/.fleet/fleet_keys.json')).read())"
python tests/smoke_test.py
```

---

## 2. Run it

Foreground (development):

```bash
python app.py        # API
python worker.py     # worker, separate terminal
```

As services, on a Linux host:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/fleet-control-plane.service systemd/fleet-worker.service ~/.config/systemd/user/
# edit User= and any paths inside both files first
systemctl --user daemon-reload
systemctl --user enable --now fleet-control-plane fleet-worker
loginctl enable-linger "$USER"     # survive logout
```

On Windows, use Task Scheduler with `python.exe app.py` / `python.exe worker.py`
and set `FLEET_HOME` as a user environment variable.

---

## 3. Health checks

```bash
curl -s localhost:8088/healthz | python -m json.tool
```

Expected: `"status":"ok"`, `"public_key_ready":true`, and a non-zero
`node_keys_configured`. `404` on the port means the API is not running;
`401` on a task call means the token does not match any `FLEET_KEY_<NODE>`.

---

## 4. Submitting work

```bash
python client_delegate.py --action fleet_health_ping
python client_delegate.py --message "build finished"
python client_delegate.py --target node-b --message "GPU box, take this"
```

The client waits for completion by default and prints
`receipt signature: VERIFIED` when the Ed25519 signature checks out.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `503 No node credentials configured` | `.env` missing or has no `FLEET_KEY_*` | `python setup_fleet.py --init` |
| `401 Unauthorized fleet key` | Token not in the roster / typo | Re-read `~/.fleet/.env`; regenerate with `--force` |
| `422` with "unknown node" | `target` not in `FLEET_NODES` | Add it and restart the API |
| Tasks stay `pending` | Worker not running, or `target` is another node | Start `worker.py` on the target node |
| `notification_status: "skipped"` | Telegram not configured | Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, restart worker |
| Task `dead_letter` | Action raised repeatedly | Inspect `error` in `GET /api/fleet/tasks/{id}` |
| `receipt signature: INVALID` | Payload mutated, or key rotated | Re-fetch `/.well-known/fleet-keys.json`; check canonical bytes unchanged |
| Port already in use | Another API instance | Change `FLEET_PORT` in `.env` |

---

## 6. Inspecting the database

```bash
sqlite3 ~/.fleet/tasks.db \
  "SELECT substr(task_id,1,8), target, action, status, error FROM fleet_tasks ORDER BY created_at DESC LIMIT 20;"

sqlite3 ~/.fleet/tasks.db \
  "SELECT status, COUNT(*) FROM notification_outbox GROUP BY status;"
```

WAL companions (`tasks.db-wal`, `tasks.db-shm`) are normal. Do not delete them
while the service is running.

---

## 7. Rotating secrets

```bash
python setup_fleet.py --init --force     # new tokens AND a new signing key
systemctl --user restart fleet-control-plane fleet-worker
```

Rotating the signing key invalidates verification of **already issued**
receipts. If that matters, back up `fleet_ed25519.key` and `fleet_keys.json`
first, or rotate only the bearer tokens by editing `.env` and restarting.

---

## 8. Backup and restore

```bash
sqlite3 ~/.fleet/tasks.db ".backup ~/fleet-backup-$(date +%F).db"
tar czf fleet-keys-$(date +%F).tgz -C ~/.fleet .env fleet_ed25519.key fleet_keys.json
```

Restore by stopping both services, putting the files back, and restarting.
Keep the key backup separate from the database: the key is what makes receipts
trustworthy.

---

## 9. Uninstall

```bash
systemctl --user disable --now fleet-control-plane fleet-worker
rm -rf ~/.fleet ~/.config/systemd/user/fleet-*.service
```

---

## 10. Known limits

* The long-poll wake signal is **per-process**. Run one API process; with
  multiple uvicorn workers the signal may not reach the worker immediately
  (the worker still picks tasks up on its next database poll).
* `gpu_batch` is declared in the allowlist but has no implementation yet; it
  returns an error and retries. A GPU node worker is a separate component.
* There is no built-in TLS. Terminate it at a reverse proxy.
* The task board at `/` is unauthenticated and read-only.
