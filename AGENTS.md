# AGENTS.md — Autonomous Agent Operating Contract

> **Authoritative instructions for AI Coding Agents (Hermes, Claude Code, OpenAI Codex, Cursor, Windsurf, Aider).**
> **Goal:** 98%+ first-attempt deterministic success rate for cross-device fleet integration — **both** shared vector memory and durable cross-node task delegation.

---

## 🧭 Step 0 — Decide Which Pipeline the Human Actually Needs

Read the request, pick one pipeline, execute it end to end. Do not install what was not asked for.

| The human says something like… | Pipeline | Go to |
|---|---|---|
| "remember this", "what did we decide about X", "share notes between my machines" | **A — Fleet Memory** (vector) | §A |
| "notify me", "run this on my other PC", "make sure it actually ran", "queue this job" | **B — Control Plane** (tasks) | §B |
| Both, or genuinely unclear | A first, then B | §A → §B |

**Deduction rules (do not interrogate the human for these):**

* More than one machine mentioned → that is a fleet. Pipeline A everywhere; Pipeline B on whichever box is always on.
* A GPU rig mentioned → its worker handles compute tasks; memory domain is `personal`.
* A corporate/managed laptop mentioned → memory domain is `work`; all fleet traffic must be outbound TLS 443 (no inbound ports, no SSH).
* **No VPS mentioned → deploy Pipeline B locally. Never assume a remote server exists.**

### 📏 Human Interaction Budget (binding)

Ask **at most one question**, and only if you truly cannot proceed.

**Never** ask the human to:
* create directories, write `.env` files, or generate keys — the bootstrap does this.
* pick a memory domain — deduce it from §A.2.
* explain or configure the task plane — that is your job.

**Never** ask about Telegram unless they asked for notifications; if they did not, deploy with Telegram disabled and say so in one line.

**Never** claim a deployment is "done", "live", or "shipped" without pasting the matching ledger (§A.4 or §B.5) — real output, not a description of it.

---

## §A — Pipeline A: Fleet Memory (cross-device knowledge)

### A.1 Install Client Dependencies

Install into the Python interpreter that backs Hermes:

```bash
# Windows (cmd / PowerShell / git-bash)
pip install "mcp[cli]" qdrant-client fastembed python-dotenv

# Linux / macOS
pip3 install "mcp[cli]" qdrant-client fastembed python-dotenv
```

### A.2 Autonomous Initialization (One Command)

```bash
# Enterprise work PC / corporate laptop
python client/fleet_memory.py --init --domain work

# Personal workstation / GPU rig
python client/fleet_memory.py --init --domain personal

# Always-on cloud host / coordinator
python client/fleet_memory.py --init --domain all

# Managed Qdrant (no server of your own)
python client/fleet_memory.py --init --url "https://xxxx.cloud.qdrant.io:6333" --key "your_api_key" --domain work
```

*(On Linux/macOS use `python3` or `sys.executable`.)*

### A.3 Node Domain Decision Matrix

If the domain was not stated, deduce it:

1. **`work`** — Windows Enterprise/Pro work laptop; MDM, Zscaler, GlobalProtect, or corporate proxy active.
   **Security rule:** only `work` + `shared` memories resolve here; personal notes never sync in.
2. **`personal`** — consumer GPU present (RTX 3070/4080/4090) or personal desktop/gaming rig.
   **Security rule:** only `personal` + `shared` memories resolve here; enterprise secrets never sync in.
3. **`all`** — headless Linux VPS running 24/7; the coordinator/Telegram hub.

### A.4 Verification Ledger A (Mandatory Deliverable)

Paste the **real** output of `python client/fleet_memory.py --init`:

```text
[1/5] Auditing environment configuration...
      * Enforced Domain: <WORK|PERSONAL|ALL>
      * Vector Target  : <URL or IP:PORT>
[2/5] Probing vector engine connectivity...
      [OK] Connected to Qdrant successfully (Latency: <X>ms)
[3/5] Bootstrapping collection & payload indexes...
      [OK] Collection 'hermes_fleet_memory' validated (384-dim COSINE)
[4/5] Configuring Hermes Agent...
      [OK] FastMCP server 'fleet-memory' registered in Hermes
      [OK] Configured 'memory.provider: none' (Zero ambient prompt bloat)
[5/5] Executing live test retrieval...
      [OK] Test vector search completed in <X>ms
```

---

## §B — Pipeline B: Fleet Control Plane (durable task delegation)

### B.1 When to deploy

Deploy when the human wants work to cross a machine boundary **durably** and **verifiably**:

* notifications pushed from a host that stays awake;
* jobs queued on a machine that may be offline right now;
* proof that something ran (a signed receipt), not just "I called the API".

**Runs with no VPS, no domain, no TLS, and no Qdrant.** Single laptop is a valid deployment.

### B.2 Install

```bash
pip install fastapi uvicorn pydantic cryptography
```

### B.3 Bootstrap (one command, non-interactive)

```bash
cd server/control-plane

# Single machine — the common case. Works immediately.
python setup_fleet.py --init

# Fleet: name this node and list every node that will run a worker.
python setup_fleet.py --init --node-id coordinator --nodes coordinator,workstation

# Only if the human asked for notifications.
python setup_fleet.py --init --telegram-token "<bot token>" --telegram-chat-id "<chat id>"
```

This is idempotent. It writes `$FLEET_HOME/.env` (0600, default `~/.fleet/.env`),
generates the Ed25519 receipt keypair, publishes the public JWKS, and creates the
SQLite WAL database. **Do not hand-create any of these files.**

### B.4 Run

```bash
python app.py      # terminal 1 — API on 127.0.0.1:8088
python worker.py   # terminal 2 — worker for this node
```

Persistent install on Linux — copy `systemd/*.service` to `~/.config/systemd/user/`,
set `User=` and paths, then `systemctl --user enable --now fleet-control-plane fleet-worker`.

On Windows use Task Scheduler with `FLEET_HOME` set as a user environment variable.

Then prove the round trip and paste the result:

```bash
python client_delegate.py --action fleet_health_ping
```

### B.5 Verification Ledger B (Mandatory Deliverable)

```text
[1/5] FLEET_HOME prepared            <path>
[2/5] Identity + roster configured   node_id=<x>  nodes=<a,b>
[3/5] Ed25519 keypair                generated|reused  <key path> + JWKS
[4/5] Task database                  <db path> (WAL)
[5/5] Verifying                      node keys=<n>  telegram=<enabled|disabled>

[x] Live round trip
    [+] accepted: <task_id> -> <node> (fleet_health_ping)
    [=] status: completed
    [*] receipt signature: VERIFIED (kid=<key id>)
```

If step 5 does not show `result: OK`, or the round trip does not show
`receipt signature: VERIFIED`, the deployment is **not** done. Report the actual
error instead of a summary.

### B.6 Node roster rules

* Every node that should execute work needs its own `worker.py` **and** an entry in `FLEET_NODES`.
* Every node gets a bearer token `FLEET_KEY_<NODE>` (uppercase, `-` → `_`) in `$FLEET_HOME/.env`.
* A worker only ever claims tasks addressed to its own `FLEET_NODE_ID`. Nodes cannot claim each other's work.
* Clients may run on any machine: `python client_delegate.py --url <host> --key <token>`.
  Remote callers can also use `~/.hermes/fleet_auth.json`:
  `{"fleet_endpoint": "https://host", "fleet_key": "flk_..."}`.

### B.7 Delegating from inside an agent (MCP)

The `fleet_task_delegate` / `fleet_task_status` MCP tools use the same plane.
They resolve the endpoint from `FLEET_TASKS_URL` (default `http://127.0.0.1:8088`)
or from `~/.hermes/fleet_auth.json`. **Never assume a remote fleet host exists** —
if the human's plane is local, that default is already correct.

Allowlisted actions only:

| Action | Payload | Effect |
|---|---|---|
| `fleet_health_ping` | `{}` | Load, pid, timestamp of the target node |
| `telegram_notify` | `{"message": "...", "photo_url": "https://..."}` | Telegram message and/or photo |
| `gpu_batch` | reserved | Compute job on a GPU node |

---

## 🚫 Hard Architectural Rules (Zero-Tolerance Violations)

1. **NEVER Enable Ambient Memory Plugins.**
   `memory.provider` stays `none`. Ambient injection dumps 3,000+ tokens on every turn and breaks reasoning. Retrieval is strictly on-demand via `fleet_memory_search`.

2. **NEVER Run Shell Execution Inside Cognitive Turns for Cross-Node Work.**
   No ad-hoc `ssh` to move work between machines. Use the task plane or memory slots.

3. **Deterministic Slot Overwrites (No Vector Pollution).**
   Always pass both `slot_name` and `client_id` to `fleet_memory_store`:
   ```python
   fleet_memory_store(
       text="Post-mortem and consensus decisions...",
       slot_name="caddy_ingress_rule",
       client_id="fleet_infra",
       target_domain="shared",
       pinned=True
   )
   ```
   Omitting `slot_name` silently falls back to episodic append mode and accumulates duplicate drift.

4. **Honest Blocker Reporting (Zero Hallucination).**
   If Qdrant, the control plane, or a peer is unreachable, report the real error. Never fabricate search results, task ids, or receipts.

5. **NEVER Commit Fleet State or Secrets.**
   `$FLEET_HOME` (`.env`, `fleet_ed25519.key`, `*.db`) is never committed. Every generated token is a bearer credential. Before any `git add`, confirm no `flk_` token, private key, or API key is staged.

6. **NEVER Change the Canonical Receipt Bytes.**
   Receipts are signed over `json.dumps({"completed_at": round(t,3), "result": r, "task_id": id}, sort_keys=True, separators=(",",":"))`. Changing this format silently invalidates every previously issued receipt. Version it instead.

7. **NEVER Add an Action That Executes Arbitrary Code.**
   The allowlist is closed (`fleet_health_ping`, `telegram_notify`, `gpu_batch`). Adding shell, eval, or free-form command execution breaks the security model — remote nodes would gain code execution.

8. **Bind to Loopback Unless There Is a TLS Terminator.**
   `FLEET_HOST=0.0.0.0` is only acceptable behind a reverse proxy that terminates TLS. Never expose the API directly to the internet.

9. **CPU Pinning Is Opt-In.**
   `CPUAffinity` ships commented out in the service templates. Enable it only when the host also runs latency-sensitive inference — pinning a normal laptop or desktop to one core is a performance regression.

10. **NEVER Store Credentials in Shared Vector Memory.**
    A credential written to a memory card is a credential published wherever that card is readable. This is not hypothetical: the coordination feed was world-readable and plaintext keys were found in it.
    * Store a **pointer** to the secret's location (`see ~/.hermes/.env`), never the value.
    * Never write a credential into a card, a task payload, a slot, or a runbook entry.
    * If a secret was ever written to memory, treat it as disclosed: **rotate it**, then redact the card.
    * Prefer loading secrets from a `0600` env file (`EnvironmentFile=`) over inline `Environment=` lines — `systemctl cat` is world-readable.
    * Ship no credential defaults in source. Fail to start instead.

---

## 🛠️ Troubleshooting & Recovery Cheatsheet

### Pipeline A — memory

| Failure Mode | Root Cause | Agent Action |
|---|---|---|
| `[WinError 10061]` / `Connection refused` | WSTunnel down or Qdrant port 6333 closed | Tell the human: *"Vector engine unreachable on port 6333 — please launch WSTunnel or start Qdrant."* |
| `HTTP 401 Unauthorized` | Missing/invalid `FLEET_QDRANT_KEY` | Re-run with `--key <256-bit-key>` |
| `FastMCP not found` | `mcp` missing in the active venv | `pip install "mcp[cli]"` |
| `Hermes CLI not found` | Hermes installed in an isolated directory | Check `$LOCALAPPDATA/hermes` or `~/.hermes`, register with the full path |

### Pipeline B — control plane

| Failure Mode | Root Cause | Agent Action |
|---|---|---|
| `503 No node credentials configured` | `.env` missing or has no `FLEET_KEY_*` | Run `python setup_fleet.py --init` |
| `401 Unauthorized fleet key` | Token typo, or not in the roster | Re-read `$FLEET_HOME/.env`; regenerate with `--init --force` |
| `422` mentioning "unknown node" | `target` absent from `FLEET_NODES` | Add it, restart the API |
| Tasks stuck `pending` | No worker on that node, or wrong `target` | Start `worker.py` on the target node |
| `notification_status: "skipped"` | Telegram not configured (expected default) | Provide `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, restart the worker |
| Task `dead_letter` | Action raised repeatedly | Read `error` on `GET /api/fleet/tasks/{id}` |
| `receipt signature: INVALID` | Payload mutated, or key rotated | Re-fetch `/.well-known/fleet-keys.json`; confirm canonical bytes unchanged (Rule 6) |
| `Address already in use` | Second API instance | Change `FLEET_PORT` in `$FLEET_HOME/.env` |
| Tasks signed but never delivered | Worker running, but Telegram creds absent | Expected: outbox marks `skipped`. Add creds to actually deliver. |
