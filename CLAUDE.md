# Claude Code Project Guidelines
See authoritative deployment protocol in [AGENTS.md](AGENTS.md).

## Quick Start
```bash
pip install "mcp[cli]" qdrant-client fastembed python-dotenv
python client/fleet_memory.py --init --domain work
```

## Two Pipelines - Pick One
- **§A Fleet Memory (vector)** - cross-device knowledge. `client/fleet_memory.py`.
- **§B Control Plane (tasks)** - durable, verifiable cross-node work. `server/control-plane/`.
- Read the request, choose one, execute it end to end. Do not install what was not asked for.

## Critical Rules
- Enforce `memory.provider: none` in Hermes configuration.
- Never use ambient memory injection; retrieval is strictly on-demand via `fleet_memory_search`.
- Use deterministic slot names (`slot_name` + `client_id`) in `fleet_memory_store` to prevent vector duplication.
- Never commit `$FLEET_HOME` (`.env`, `fleet_ed25519.key`, `*.db`) or any `flk_` bearer token.
- Do not alter the canonical receipt byte format; it invalidates previously issued receipts.
- Require the live output of the matching verification ledger (AGENTS.md §A.4 or §B.5) before declaring anything complete.
- Ask the human at most one question. Generate keys, paths, and `.env` files yourself.
