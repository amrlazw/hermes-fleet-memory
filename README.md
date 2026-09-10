# hermes-fleet-memory

> **Zero-bloat distributed vector memory, hardware-enforced domain firewalls, and NAT-traversing execution mesh for multi-instance Hermes agent fleets.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![FastMCP](https://img.shields.io/badge/Protocol-FastMCP%202.x-green.svg)](https://modelcontextprotocol.io/)
[![Qdrant](https://img.shields.io/badge/Vector%20Engine-Qdrant-red.svg)](https://qdrant.tech/)
[![Zero Ambient Bloat](https://img.shields.io/badge/Prompt%20Overhead-0%20Tokens-brightgreen.svg)]()

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   HERMES FLEET MESH                    │
                    └────────────────────────────────────────────────────────┘
                                                │
       ┌────────────────────────────────────────┼────────────────────────────────────────┐
       │                                        │                                        │
┌──────────────┐                         ┌──────────────┐                         ┌──────────────┐
│    NODE 1    │                         │    NODE 2    │                         │    NODE 3    │
│  Central Hub │                         │   Work PC    │                         │  Home Rig    │
│  (Cloud VPS) │                         │  (Corporate) │                         │  (Workstation)│
└──────┬───────┘                         └──────┬───────┘                         └──────┬───────┘
       │                                        │                                        │
       │ Telegram Gateway (@Bot)                │ Corporate Zscaler / MDM                │ Local GPU Inference
       │ FLEET_HARD_DOMAIN=all                  │ FLEET_HARD_DOMAIN=work                 │ FLEET_HARD_DOMAIN=personal
       │ FastMCP stdio client                   │ FastMCP stdio client                   │ FastMCP stdio client
       │                                        │                                        │
       └───────────────────┬────────────────────┴───────────────────┬────────────────────┘
                           │                                        │
                           ▼                                        ▼
             ┌──────────────────────────┐             ┌──────────────────────────┐
             │     Qdrant Vector DB     │             │  Desktop Bridge (:8099)  │
             │ (VPS Native or Managed)  │             │ (Live Exec & File Read)  │
             └──────────────────────────┘             └──────────────────────────┘
```

---

<!-- ============================================================================== -->
<!-- AGENT RUNBOOK CONTRACT: READ THIS FIRST -->
<!-- ============================================================================== -->
## 🤖 For AI Coding Agents: Autonomous Deployment Contract

> **Full autonomous protocol, OS decision trees, and non-interactive flags:** See [AGENTS.md](AGENTS.md).
> The contract covers **both** pipelines — cross-device vector memory (§A) and the cross-node task plane (§B) — including when to pick each, and the mandatory verification ledger for each.

If you are an AI Coding Agent (Hermes, Claude Code, Codex, Cursor, Windsurf) instructed by your human to deploy this repository, execute the following deterministic protocol without open-ended interview loops:

### 1. Install Dependencies
Install in the active Python environment:
```bash
pip install "mcp[cli]" qdrant-client fastembed python-dotenv
```

### 2. Autonomous Initialization (One Command)
Run the auto-provisioning initializer with the appropriate domain:
```bash
# Enterprise Work PC (Restricts to work + shared):
python client/fleet_memory.py --init --domain work

# Personal GPU Rig / Desktop (Restricts to personal + shared):
python client/fleet_memory.py --init --domain personal

# Sovereign Cloud Hub (Omniscient):
python client/fleet_memory.py --init --domain all

# Qdrant Cloud (Managed):
python client/fleet_memory.py --init --url "https://xxxx.cloud.qdrant.io:6333" --key "your_api_key" --domain work
```

### 3. Deliver the 5-Point Verification Ledger
Do not declare deployment complete without outputting the live confirmation from step 2 (`[OK] Connected`, `[OK] Collection validated`, `[OK] FastMCP registered`, `[OK] Zero-bloat verified`, `[OK] Test vector retrieved`).
<!-- ============================================================================== -->
<!-- END AGENT RUNBOOK CONTRACT -->
<!-- ============================================================================== -->

---

## The Problem with Current Agent Memory

Developers operating multiple instances of [Hermes Agent](https://github.com/NousResearch/hermes-agent) (e.g. a 24/7 VPS Telegram bot, an enterprise work laptop, and a personal workstation) face three painful bottlenecks:

1. **The Silo Trap (Amnesia Across Machines):**  
   Your mobile Telegram bot knows nothing of the architectural decisions made on your desktop. Your work laptop cannot reference deployment runbooks or shell cheatsheets created at home.
2. **The Ambient Bloat Trap (Context Fatigue):**  
   Traditional memory plugins (Mem0, naive system prompt dumps) inject 2,000 to 5,000 tokens of unstructured memories into the system prompt on **every single conversational turn**. This burns API budgets, slows responses, and degrades the LLM's core reasoning.
3. **The Enterprise Data Leakage Risk:**  
   Syncing flat memory between work and personal devices risks leaking confidential enterprise API keys or client architectures into personal chats.

---

## Real-World Use Cases: What Breaks Today vs. Fleet Memory

| Real Scenario | What Happens Without Fleet Memory | What Happens With `hermes-fleet-memory` |
| :--- | :--- | :--- |
| **"What was the reverse proxy header we settled on for our staging Caddy server?"** | Agent says: *"I have no record of that conversation."* (Trapped in home PC's local SQLite). | Searches `domain="shared"`, retrieves verified Caddy config snippet with `score: 0.84`, prints exact directive. |
| **"Check my desktop GPU thermals while I'm at dinner."** | VPS says: *"I cannot reach your home PC; it is behind residential NAT without a public IP."* | Calls `desktop_status()` over reverse WSTunnel: *"RTX 3070 Ti is at 41°C, 16W idle, GDDR6X @ 9,901 MHz."* |
| **"Check my desktop GPU" (When PC is powered off).** | Agent hangs, times out, or runs `nvidia-smi` on the VPS itself (which has no GPU). | Detects offline bridge in 3s and falls back to fleet memory card: *"PC is powered off. Baseline: 0.925V @ 1950MHz."* |
| **"Remember this client webhook secret for our enterprise staging env."** | Naive memory sync leaks enterprise secrets into personal gaming/crypto chats. | Tagged under `domain="work"`. Personal PC physically cannot query it. Strict client-level firewall. |
| **"Hello, how are you?"** | Traditional memory injects 4,000 tokens into the prompt, burning API tokens on a greeting. | **Zero ambient injection.** `memory.provider: none`. Retrieval is strictly on-demand. Cost: $0.00. |
| **"I updated my desktop RAM to 64GB."** | Flat stores append another vector. Agent hallucinates: *"You have 32GB, or possibly 64GB."* | **Deterministic UUID5 slot overwrite.** Replaces `desktop_hardware:ram` point in-place. Zero duplicate drift. |

---

## Architecture: The Three Pillars of Paradigm E++

1. **Zero Ambient Prompt Overhead (`memory.provider: none`):**  
   Memories reside in a central 384-dimensional vector database. Retrieval occurs strictly **on-demand** via FastMCP tool calls (`fleet_memory_search`). Zero tokens are wasted on conversational turns where memory is irrelevant.
2. **Hardware-Enforced 3-Domain Firewall:**  
   Data is partitioned into `work`, `personal`, and `shared` vaults. Isolation is enforced at the client environment level (`FLEET_HARD_DOMAIN`), not left to probabilistic LLM prompt compliance.
3. **Deterministic Slot Invalidation (UUID5):**  
   Updating a configuration slot (e.g. `client_id="hardware"`, `slot_name="gpu_profile"`) generates an ID using `UUID5(DNS, f"{domain}:{client_id}:{slot_name}")`. Updates replace existing records in-place. Conflicting duplicate memories cannot accumulate.

---

## Deployment Models

Choose the architecture that matches your setup:

| Option | Infrastructure Needed | Cost | Setup Time | Best For |
| :--- | :--- | :--- | :--- | :--- |
| **Option A: Self-Hosted VPS** | Any Linux VPS (Oracle Free Tier, Hetzner, DO) | $0 / month | 5 minutes | Operators who want full sovereign control over data and TLS. |
| **Option B: Managed Cloud** | **No VPS needed** (Qdrant Cloud Free Tier) | **$0 / month** | **2 minutes** | **95% of users** wanting zero-DevOps cross-device memory. |
| **Option C: Full Fleet Mesh** | Home PC + Relay VPS | $0 / month | 10 minutes | Remote shell command execution & file retrieval behind NAT. |
| **Option D: Local Task Plane** | **None** (runs on machines you already have) | **$0 / month** | **2 minutes** | Durable, cryptographically verified cross-node task delegation & notifications. See [`server/control-plane`](server/control-plane/README.md). |

---

### Option A: Self-Hosted VPS (Docker / Native)

Ideal for operators running an Oracle Cloud Always-Free ARM64 VPS, Hetzner, or DigitalOcean:

```bash
git clone https://github.com/amrlazw/hermes-fleet-memory.git
cd hermes-fleet-memory/server

# 1. Generate 256-bit cluster secret
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Configure Caddy TLS Gatekeeper
cp Caddyfile.example Caddyfile
# Edit Caddyfile with your domain (e.g. brain.yourdomain.com) and token

# 3. Launch the Stack
export FLEET_QDRANT_KEY="your_256bit_token"
docker compose up -d
```

*(For bare-metal deployments without Docker, native systemd units with a ~450MB RAM footprint are provided in `server/systemd/`).*

---

### Option B: Managed Cloud (No-VPS / Zero-DevOps)

If you **do not own a VPS** and want multi-machine memory in 2 minutes:

1. Create a free account at [Qdrant Cloud](https://cloud.qdrant.io/).
2. Launch a **1GB Free Tier Cluster** ($0 permanent free tier, holding 500,000+ memory vectors).
3. Copy your **Cluster URL** (`https://xxxx.cloud.qdrant.io:6333`) and **API Key**.
4. Configure each client machine's `.env`:
   ```ini
   FLEET_QDRANT_URL=https://xxxx.cloud.qdrant.io:6333
   FLEET_QDRANT_KEY=your_qdrant_cloud_api_key
   FLEET_QDRANT_HTTPS=true
   ```
*Done. All Hermes instances now share persistent vector memory across the cloud.*

---

### Option C: Full Fleet Mesh & Remote Execution Bridge

For operators who want their 24/7 cloud node (e.g. Telegram bot) to **execute live commands** (`nvidia-smi`, build scripts) and **retrieve files** from their home workstation behind residential NAT:

```
[ Telegram on Phone ] ──► [ Cloud VPS ] ──(Reverse WSTunnel TLS 443)──► [ Home PC Bridge (:8099) ]
```

1. **Launch Desktop Bridge on Workstation:**
   ```bash
   python client/desktop_bridge.py
   ```
2. **Start Reverse WSTunnel:**
   - **Linux / macOS:** `client/start-tunnel.sh`
   - **Windows:** `client/start-tunnel.vbs` (runs completely silently at logon without prompt windows).
3. **Unlocked Capabilities:**
   - `desktop_status`: Returns live GPU temperature, VRAM usage, and workstation heartbeat.
   - `desktop_exec`: Executes safe, sandboxed shell commands remotely.
   - `desktop_read_file`: Fetches authorized documents under user home directory.
   - `desktop_power`: Gracefully initiates remote shutdown, restart, or abort with customizable delay.

---

### Option D: Local Task Plane (No VPS, No Docker)

Durable cross-node task delegation with cryptographically verifiable completion
receipts. Runs on machines you already own — a single laptop is a valid deployment.

```bash
cd server/control-plane
pip install fastapi uvicorn pydantic cryptography
python setup_fleet.py --init          # writes ~/.fleet/.env, keys, database
python app.py                         # API on 127.0.0.1:8088
python worker.py                      # worker for this node

python client_delegate.py --action fleet_health_ping
# -> status: completed
#    receipt signature: VERIFIED
```

* **No VPS required.** Bind to loopback; add a TLS proxy only when you want remote peers.
* **Telegram optional.** Without credentials, notification tasks complete as `skipped` — never a dead-letter loop.
* **Closed action allowlist.** `fleet_health_ping`, `telegram_notify`, `gpu_batch`. No arbitrary code execution.
* Ed25519 receipts let any peer verify a task ran, independently of the server that issued it.

Full operations guide: [`server/control-plane/RUNBOOK.md`](server/control-plane/RUNBOOK.md)

---

## Client Setup (Every Machine)

### 1. Install Dependencies
```bash
pip install "mcp[cli]" qdrant-client fastembed python-dotenv
```

### 2. Configure Environment
Copy `client/.env.example` to your Hermes environment (e.g. `~/.hermes/.env` or `%LOCALAPPDATA%\hermes\profiles\<profile>\.env`):

```ini
# Domain Isolation: "work", "personal", "shared", or "all"
FLEET_HARD_DOMAIN=work

# Point to Option A (VPS) or Option B (Qdrant Cloud)
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY=your_cluster_secret_or_cloud_key
FLEET_QDRANT_HTTPS=false
```

### 3. Initialize & Register Node (One-Click)
```bash
python client/fleet_memory.py --init
```
This automatically verifies endpoint connectivity, creates collection payload indexes, registers `fleet-memory` in Hermes, and disables ambient prompt injection (`memory.provider: none`).

Verify discovery:
```bash
hermes mcp test fleet-memory
```

---

## Frequently Asked Questions (FAQ)

#### Q: How does Option C pierce corporate Zscaler or home NAT without port forwarding?
The connection is established **outbound-only** from your workstation to the cloud over standard HTTPS (port 443). `wstunnel` encapsulates raw TCP traffic inside standard WebSocket frames with a 20-second ping frequency and frame masking. Corporate Deep Packet Inspection (DPI) engines like Zscaler see standard web traffic. Once established, the tunnel allows reverse multiplexing back into the workstation's loopback interface (`127.0.0.1:8099`).

#### Q: What stops someone on the internet from sending commands to my home PC?
**Five concentric security rings:**
1. Caddy drops any request lacking the 256-bit pre-shared key (`X-Fleet-Key`) with HTTP 403.
2. The desktop bridge binds strictly to `127.0.0.1` (never exposed to LAN or WAN).
3. Every bridge invocation requires `Authorization: Bearer <key>` verified with constant-time `hmac.compare_digest`.
4. Filesystem reads are hard-jailed to your user home directory; sensitive files (`.ssh/id_*`, `.env`, SAM hives) are blacklisted.
5. Destructive commands (`shutdown`, `format`, `diskpart`, `rmdir /s`) are rejected by regex filters with a 30-second hard execution timeout.

#### Q: Is Qdrant Cloud 1GB Free Tier really enough for an agent's lifetime?
Yes. Embeddings generated by `BAAI/bge-small-en-v1.5` have 384 dimensions. At FP32 precision, each vector occupies ~1.5 KB. With payload indexing metadata, 1GB of RAM comfortably accommodates over **500,000 distinct memory records**. An operator saving 20 detailed technical notes per day would take over 68 years to exhaust the free quota.

---

## Benchmarks & Performance Evidence

Measured on Oracle Cloud ARM64 (A1.Flex) and Windows 11 (x86_64 AVX2):

- **Local Embedding Latency (`bge-small-en-v1.5`):** ~14ms per chunk (local ONNX runtime).
- **Vector Search Execution:** 8ms – 18ms against indexed collections.
- **Cross-Architecture Cosine Parity:** Verified at `0.8389` (ARM64 NEON) vs `0.8390` (x86_64 AVX2).
- **Tunnel Latency Overhead:** <4ms additional round-trip latency over TLS WebSocket.

---

## License

MIT © 2026 Mohamad Amirul Azwan
