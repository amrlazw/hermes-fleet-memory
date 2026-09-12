<div align="center">

<a href="https://github.com/amrlazw/hermes-fleet-memory">
  <img src="assets/banner.svg" alt="Hermes Fleet Memory & Synapse Mesh" width="100%">
</a>

<p align="center">
  <a href="https://fleet.republikus.my/api/telemetry/badge.svg"><img src="https://fleet.republikus.my/api/telemetry/badge.svg" alt="Fleet Synapse"></a>
  <a href="https://github.com/amrlazw/hermes-fleet-memory/actions"><img src="https://img.shields.io/badge/CI_BUILD-PASSING-059669?style=flat-square&logo=githubactions&logoColor=white&labelColor=111827" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/LICENSE-MIT-3b82f6?style=flat-square&logo=opensourceinitiative&logoColor=white&labelColor=111827" alt="License"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/FASTMCP-2.X_READY-10b981?style=flat-square&logo=anthropic&logoColor=white&labelColor=111827" alt="FastMCP"></a>
  <a href="https://qdrant.tech/"><img src="https://img.shields.io/badge/VECTOR_DB-QDRANT_INT8-ef4444?style=flat-square&logo=qdrant&logoColor=white&labelColor=111827" alt="Qdrant"></a>
  <a href="#"><img src="https://img.shields.io/badge/PROMPT_OVERHEAD-0_TOKENS-06b6d4?style=flat-square&logo=speedtest&logoColor=white&labelColor=111827" alt="Zero Overhead"></a>
  <a href="#"><img src="https://img.shields.io/badge/ARCHITECTURE-PARADIGM_E%2B%2B-8b5cf6?style=flat-square&logo=hyper&logoColor=white&labelColor=111827" alt="Paradigm E++"></a>
  <a href="#"><img src="https://img.shields.io/badge/PYTHON-3.10%2B-f59e0b?style=flat-square&logo=python&logoColor=white&labelColor=111827" alt="Python 3.10+"></a>
</p>

</div>

---

### What is Paradigm E++?

**Paradigm E++** (*Epistemic State, Vector Embeddings, Distributed Execution Mesh*) is the formal architectural specification underlying Hermes Fleet Synapse:

1. **Zero Ambient Prompt Bloat (`memory.provider: none`):** Memory is never ambiently stuffed into the LLM system prompt. Retrieval is on-demand via explicit FastMCP vector searches (`fleet_synapse_search` / `fleet_memory_search`), cutting prompt costs to zero for turns where memory is unnecessary.
2. **Deterministic State Resolution (UUID5 + LWW):** Overwrites stale facts in-place using deterministic DNS-namespace UUID5 hashes (`domain:client_id:slot_name`), combined with **Last-Write-Wins (LWW)** timestamped validation to prevent out-of-order split-brain corruption.
3. **Infrastructure-Enforced Domain Firewalls (`FLEET_HARD_DOMAIN`):** Strict client-level boundary gates prevent enterprise data from cross-contaminating personal workstations, eliminating reliance on probabilistic LLM compliance.

---

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
       │ Qdrant Vector Engine (:6333)           │ Outbound WSTunnel (TLS 443)            │ Desktop Bridge (:8099)
       │ Task Queue Plane (:8088)               │ Outbound FastMCP Task Client           │ Ollama Rig / RTX 3070 Ti
       ▼                                        ▼                                        ▼
```

### Sovereign Topology & Roles

| Node | Environment | Domain Guard | Authority & Mandates |
| :--- | :--- | :--- | :--- |
| **Node 1 (`chester`)** | Oracle Cloud SG ARM64 VPS | `all` | 24/7 Coordinator, Qdrant Vector Core, Telegram Gatekeeper (`@RepublikusBot`), Central Task Control Plane. |
| **Node 2 (`wolf`)** | Enterprise Work PC (Win 11) | `work` | Corporate Presales AI Engineer, MDM/Zscaler-traversing WSTunnel, RFP/Architecture evaluation. |
| **Node 3 (`winston`)** | Personal PC Rig (Win 11 Pro) | `personal` | Technical Butler, RTX 3070 Ti Local GPU Inference, Autonomous Startup Task Ingress, Desktop Automation. |

---

### Features & Capabilities

- **Autonomous Startup Task Ingress (`client/fleet_startup_sync.py`):** Nodes automatically connect on boot/resume, pull queued tasks asynchronously from Node 1, dispatch an executive Telegram briefing before work begins, and return Ed25519-signed completion receipts.
- **NAT & Firewall Traversal (WSTunnel over TLS 443):** Enterprise workstations behind strict corporate proxies (e.g. Zscaler) maintain continuous outbound tunnels with zero exposed ports or router configuration.
- **Anonymous Architecture Telemetry:** Non-blocking opt-out compliant telemetry tracking real-world deployments via `https://fleet.republikus.my/api/telemetry/beacon` with dynamic SVG Shields badges.
- **Sub-15ms Vector Recall:** INT8 Scalar Quantization reduces memory overhead by 4x while maintaining 99%+ recall precision across multi-thousand token contexts.
