# Claude Code Project Guidelines
See authoritative deployment protocol in [AGENTS.md](AGENTS.md).

## Quick Start
```bash
pip install "mcp[cli]" qdrant-client fastembed python-dotenv
python client/fleet_memory.py --doctor                 # bounded preflight, always exits
python client/fleet_memory.py --init --domain work     # work | personal | all
```

## Never run the server bare in a shell
`client/fleet_memory.py` with **no arguments** is an MCP stdio server: it blocks forever
waiting for JSON-RPC on stdin. From a shell or an agent tool call that is an unrecoverable
hang, not a crash — there is no output to diagnose.

- Inspect a node with `--doctor`. It is bounded, never starts the server, and exits
  non-zero on failure. Use it instead of launching the server "to see if it works".
- Set a node up with `--init --domain <work|personal|all>`.
- `--serve` starts the blocking server deliberately.
- Unknown flags exit `2` with usage; they never fall through to the server.
- Pre-download the embedding model with `--warm`, or the first search stalls
  for minutes while it fetches ~130MB.
- Register with Claude Code:
  `claude mcp add fleet-synapse -- python /abs/path/client/fleet_memory.py`

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
