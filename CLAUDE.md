# Claude Code Project Guidelines
See authoritative deployment protocol in [AGENTS.md](AGENTS.md).

## Quick Start
```bash
pip install "mcp[cli]" qdrant-client fastembed python-dotenv
python client/fleet_memory.py --init --domain work
```

## Critical Rules
- Enforce `memory.provider: none` in Hermes configuration.
- Never use ambient memory injection; retrieval is strictly on-demand via `fleet_memory_search`.
- Use deterministic slot names (`slot_name` + `client_id`) in `fleet_memory_store` to prevent vector duplication.
- Require live output of the 5-point verification ledger before declaring tasks complete.
