---
name: fleet-memory
description: Distributed vector memory and remote workstation execution bridge for Hermes agent fleets.
version: 1.0.0
author: Amirul Azwan
license: MIT
---

# Fleet Memory (hermes-fleet-memory)

This skill integrates the `fleet_memory_search` and `fleet_memory_store` MCP tools into Hermes, providing zero-ambient-bloat distributed vector memory across multiple nodes (VPS, Work PC, Personal Rig).

## Essential Guidance
- **Vector Retrieval Over Shell Probes:** When asked about hardware configurations, enterprise payment architectures, or past decisions on a remote machine, **ALWAYS call `fleet_memory_search(query=...)` first**. Do not run local bash/PowerShell probes expecting remote visibility.
- **Deterministic Slots:** When saving configurations, pass both `slot_name` and `client_id` to update records in-place without duplicate drift.

## Tools Reference

### 1. `fleet_memory_search`
Search the fleet memory for facts, runbooks, or configurations:
- `query` (string, required): The topic or inquiry.
- `target_domain` (string, optional): "personal", "work", "shared", or "all".

### 2. `fleet_memory_store`
Store or update an authoritative card:
- `text` (string, required): Factual statement or markdown documentation.
- `slot_name` (string, optional): Deterministic slot (e.g. `gpu_profile`, `caddy_template`).
- `client_id` (string, optional): Subsystem tag (e.g. `desktop_hardware`, `payment_gateway`).
- `target_domain` (string, optional): "personal", "work", or "shared".
- `pinned` (bool, optional): Protect from 90-day episodic expiry cleaner.

### 3. `desktop_status` (Option C - Fleet Mesh)
Check if the remote workstation is online and retrieve live GPU metrics (temperature, utilization, VRAM usage).

### 4. `desktop_exec` (Option C - Fleet Mesh)
Execute a safe terminal command on the remote workstation (e.g. `nvidia-smi`, undervolt scripts).

### 5. `desktop_read_file` (Option C - Fleet Mesh)
Read an authorized file from the remote workstation under the user directory.

### 6. `desktop_power` (Option C - Fleet Mesh)
Gracefully manage the remote workstation's power state from your cloud daemon:
- `action` (string, default "shutdown"): "shutdown", "restart", or "cancel".
- `delay_seconds` (int, default 60): Grace buffer before execution (allows cancellation).

## Multi-Agent Persona Synchronization Pattern
When running different personas across fleet nodes (e.g. a desktop butler agent on Node 3 and a cloud hub on Node 1), prevent identity fragmentation by committing a shared persona slot:
```python
fleet_memory_store(
    text="Fleet Agents:\n- Node 3 (Desktop): Winston (Personal butler & GPU aide-de-camp)\n- Node 1 (VPS): Hermes (Cloud hub & Telegram gateway)\n- Node 2 (Laptop): Work Agent (Enterprise solutions)",
    slot_name="fleet_personas",
    client_id="fleet_identity",
    target_domain="shared",
    pinned=True
)
```
Every agent across the mesh can now query `fleet_memory_search(query="who is Winston?")` and resolve peer identities instantly.
