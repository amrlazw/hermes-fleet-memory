# AGENTS.md — Autonomous Agent Operating Contract
> **Authoritative instructions for AI Coding Agents (Hermes, Claude Code, OpenAI Codex, Cursor, Windsurf, Aider).**
> **Goal:** 98%+ first-attempt deterministic success rate for cross-device fleet memory integration.

---

## ⚡ Zero-Ambiguity One-Command Bootstrap

Do not guess file paths, do not write custom setup scripts, and do not stall the user with open-ended interview loops if context is already apparent. Execute the exact deterministic pipeline below:

### 1. Install Client Dependencies
Install into the active Python interpreter currently backing Hermes:
```bash
# Windows (cmd / PowerShell / git-bash)
pip install "mcp[cli]" qdrant-client fastembed python-dotenv

# Linux / macOS
pip3 install "mcp[cli]" qdrant-client fastembed python-dotenv
```

### 2. Autonomous Initialization (One Command)
Run the auto-provisioning initializer with explicit flags:

```bash
# If host is an Enterprise Work PC / Corporate Laptop:
python client/fleet_memory.py --init --domain work

# If host is a Personal Workstation / GPU Rig:
python client/fleet_memory.py --init --domain personal

# If host is a Sovereign Cloud VPS / Telegram Hub:
python client/fleet_memory.py --init --domain all

# If using Qdrant Cloud (Managed, no VPS needed):
python client/fleet_memory.py --init --url "https://xxxx.cloud.qdrant.io:6333" --key "your_api_key" --domain work
```

*(On Linux / macOS, substitute `python` with `python3` or `sys.executable`).*

---

## 🎯 Autonomous Node Domain Decision Matrix

If the human user did not explicitly state the domain, deduce it deterministically:
1. **`domain: work`**
   * Host is Windows 11 Enterprise / Pro on a work laptop.
   * Host has MDM, Zscaler, GlobalProtect, or corporate proxies active.
   * **Security Rule:** Prevents personal notes from syncing here. Only `work` + `shared` memories are accessible.
2. **`domain: personal`**
   * Host has an active local consumer GPU (e.g. NVIDIA RTX 3070, 4080, 4090).
   * Host is personal desktop or gaming rig.
   * **Security Rule:** Prevents enterprise work secrets from syncing here. Only `personal` + `shared` memories are accessible.
3. **`domain: all`**
   * Host is a Linux VPS (Oracle Cloud, Hetzner, DigitalOcean) running headless 24/7.
   * Acts as the omniscient Telegram gatekeeper or central coordinator.

---

## 📋 The 5-Point Verification Ledger (Mandatory Deliverable)

An agent **MUST NEVER** declare deployment "done", "live", or "shipped" without producing the live output from `python client/fleet_memory.py --init`. Your final turn to the user must contain the real output confirming:

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

## 🚫 Hard Architectural Rules (Zero-Tolerance Violations)

1. **NEVER Enable Ambient Memory Plugins:**
   * Do not set `memory.provider` to `local`, `mem0`, or anything other than `none`.
   * Ambient injection dumps 3,000+ tokens on every greeting turn and breaks reasoning. Retrieval is **strictly on-demand** via `fleet_memory_search`.
2. **NEVER Run Shell Execution Inside Cognitive Turns for Cross-Node Work:**
   * If asked to trigger work on another machine, do not execute random `ssh` commands. Use the designated fleet task plane or memory slots.
3. **Deterministic Slot Overwrites (No Vector Pollution):**
   * When storing architectural decisions or hardware runbooks, **ALWAYS** pass both `slot_name` and `client_id` to `fleet_memory_store`:
     ```python
     fleet_memory_store(
         text="Post-mortem and consensus decisions...",
         slot_name="caddy_ingress_rule",
         client_id="fleet_infra",
         target_domain="shared",
         pinned=True
     )
     ```
   * Omitting `slot_name` falls back to episodic append mode, accumulating duplicate drift.
4. **Honest Blocker Reporting (Zero Hallucination):**
   * If Qdrant or WSTunnel is unreachable, report the connection error honestly. Never fabricate simulated search results or pretend memory was stored when the database returned a connection error.

---

## 🛠️ Troubleshooting & Recovery Cheatsheet

| Failure Mode | Root Cause | Agent Action |
|---|---|---|
| `[WinError 10061]` / `Connection refused` | WSTunnel is not running or Qdrant port 6333 is closed. | Tell user: *"Vector engine unreachable on port 6333. Please launch WSTunnel or start Qdrant."* |
| `HTTP 401 Unauthorized` | Missing or invalid `FLEET_QDRANT_KEY`. | Re-run with `--key <256-bit-key>`. |
| `FastMCP not found` | `mcp` library missing in active venv. | Run `pip install "mcp[cli]"`. |
| `Hermes CLI not found` | Hermes installed in isolated directory. | Check `$LOCALAPPDATA/hermes` or `~/.hermes` and register using full path. |
