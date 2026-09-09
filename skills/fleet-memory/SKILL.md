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
