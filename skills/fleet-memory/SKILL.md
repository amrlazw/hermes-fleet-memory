---
name: fleet-memory
description: Use when recalling or storing architecture, hardware specs, GPU settings, payment APIs, or cross-node notes across the Hermes fleet.
version: 1.2.0
author: Amirul Azwan
license: MIT
---

# Fleet Memory & Sovereign Mesh (Paradigm E++)

Universal on-demand vector memory, domain-isolated vaults, and remote execution mesh linking Node 1 (Chester / VPS), Node 2 (Wolf / Corporate PC), and Node 3 (Winston / Personal PC).

## Fundamental Rule: Vector Retrieval Over Local Shell Commands
When the user asks about:
- Personal desktop hardware specs, RTX 3070 Ti undervolting, or thermal profiles
- Enterprise payment gateway configurations (DOKU, SenangPay, webhooks)
- Infrastructure baselines, Oracle Cloud VPS setups, Caddy routing, or homelab specs
- Architectural notes, past decisions, or multi-node state

**DO NOT attempt to execute local bash commands on the host to inspect a remote machine.**  
**ALWAYS call `fleet_memory_search(query=...)` first.** The fleet vector store holds the authoritative state cards for all nodes.

---

## Domain Firewall Rules (Host-Environment Enforced)
- **Node 1 (Chester - VPS):** `FLEET_HARD_DOMAIN=all`. Can query and store across all domains.
- **Node 2 (Wolf - Work PC):** `FLEET_HARD_DOMAIN=work`. Can only query/store `work` and `shared`. Attempting to access `personal` triggers an immediate `PermissionError`.
- **Node 3 (Winston - Rig):** `FLEET_HARD_DOMAIN=personal`. Can only query/store `personal` and `shared`. Attempting to access `work` triggers an immediate `PermissionError`.

---

## Tools Reference

### 1. `fleet_memory_search`
Query fleet vector memory on-demand:
- `query` (str): Search inquiry (e.g. "RTX 3070 Ti undervolt", "DOKU webhook secret").
- `target_domain` (optional): "personal", "work", "shared", or "all" (must match node permissions).
- `limit` (int, default 5): Maximum cards to return.

### 2. `fleet_memory_store`
Store or update knowledge in the vector store:
- `text` (str): Authoritative factual markdown or documentation.
- `slot_name` (optional): **Track A Deterministic Slot** (e.g. `gpu_profile`, `vps_caddy_spec`). Generates deterministic UUID5 ID for $O(1)$ in-place overwrites. Automatically pinned.
- `client_id` (optional): Component tag (e.g. `desktop_hardware`, `doku_gateway`).
- `target_domain` (optional): "personal", "work", or "shared".
- `pinned` (bool): If True, protects episodic records from the 90-day cleaner.
- **Semantic Deduplication:** If `slot_name` is omitted (Track B episodic), the engine automatically checks for existing memories with $\ge 0.95$ cosine similarity. Near-verbatim notes refresh the existing point in-place with an incremented revision rather than bloating the index.
- **Provenance:** Automatically tags every vector with `author_node` (`winston`, `wolf`, `chester`) and monotonic `revision`.

### 3. `desktop_status`
Query live telemetry from the Windows 11 Personal PC (Node 3):
- Returns real-time RTX 3070 Ti stats: temperature, utilization %, and VRAM usage.
- If the PC is offline or bridge unreachable, gracefully informs the user and falls back to fleet memory baseline specs.

### 4. `desktop_exec`
Execute an allowlisted diagnostic action or command on the Personal PC:
- **Preferred:** Pass `action` with a pre-declared envelope:
  - `action="gpu_status"` (nvidia-smi telemetry)
  - `action="git_status"` (repo status)
  - `action="git_log"` (recent 5 commits)
  - `action="ollama_ps"` (local LLM process status)
  - `action="whoami"` (user verification)
  - `action="system_uptime"` (workstation uptime)
- **Alternative:** Pass `command` for tokenized `shell=False` execution. Only allowlisted binaries (`nvidia-smi`, `git`, `ollama`, `tasklist`, `pgrep`, `whoami`, `python`, `node`) are permitted. Arbitrary shells (`powershell`, `cmd`, `bash`) are rejected by defense policy.

### 5. `desktop_read_file`
Read an authorized file from the Personal PC:
- `path` (str): Absolute path under user home directory (e.g. `C:/Users/dontlookie/sales-handover/notes.md`).
- Security: Strictly jailed to allowed root; blocked from accessing credentials (`.ssh`, `.env`, `id_rsa`, `SAM`). Max 5MB.

### 6. `fleet_task_delegate`
Asynchronously dispatch a background task to another node:
- `target_node`: `"chester"` (VPS) or `"winston"` (Rig).
- `action`: `"telegram_notify"`, `"fleet_health_ping"`, or `"gpu_batch"`.
- `params`: Parameters dictionary (e.g. `{"message": "Alert from Wolf"}`).

### 7. `fleet_task_status`
Check execution state and verify **Ed25519 cryptographic completion receipts**:
- `task_id` (str): Returned from `fleet_task_delegate`.
- `verify_receipt` (bool, default True): Verifies digital signature against the fleet JWKS endpoint.

---

## Local Terminal CLI (`fleet`)
To quickly inspect live fleet vitals from any terminal on Node 3:
```bash
fleet          # Render high-density ASCII bento telemetry dashboard
fleet raw      # Output raw JSON payload
```
