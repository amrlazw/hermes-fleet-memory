# Security Policy & Threat Model

This document outlines the security architecture, threat model, and defense-in-depth mechanisms governing **hermes-fleet-memory** and the **Paradigm E++** distributed agent mesh.

---

## 1. Architectural Security Philosophy: Paradigm E++

Unlike naive agent memory systems that rely on probabilistic system-prompt compliance (*"Please do not mention confidential client data"*), **Paradigm E++** enforces security boundaries at the **infrastructure and protocol layers**:

1. **Deterministic Isolation Over Prompt Compliance:**  
   The client environment enforces `FLEET_HARD_DOMAIN`. If a personal workstation requests work-domain records, the client runtime raises an immediate `PermissionError` before any network packet is dispatched.
2. **Zero Ambient Token Bloat:**  
   Setting `memory.provider: none` ensures no memory vectors are ambiently injected into the LLM's system prompt. Context injection occurs strictly via explicit, authorized FastMCP tool invocations (`fleet_memory_search`).
3. **Outbound-Only Ingress Evasion:**  
   NAT traversal is achieved without exposing inbound listening ports on enterprise workstations, preventing LAN lateral movement and corporate MDM alerts.

---

## 2. Threat Model & Attack Vectors

| Attack Vector | Threat Scenario | Defense Mechanism | Test Verification |
| :--- | :--- | :--- | :--- |
| **Cross-Domain Memory Exfiltration** | Prompt injection tricks an agent on a Personal PC into querying enterprise financial secrets. | Client-level domain firewall (`validate_domain_access`) rejects queries outside `{FLEET_HARD_DOMAIN, 'shared'}` with `PermissionError`. | `tests/test_domain_isolation.py` |
| **Concurrent Memory Corruption (Split-Brain)** | Disconnected node comes online and flushes stale cached updates over newer facts. | Timestamped **Last-Write-Wins (LWW)** and monotonic revision tracking rejects out-of-order writes. | `tests/test_lww_concurrency.py` |
| **Arbitrary File Traversal via MCP** | Remote agent requests `desktop_read_file(path="../../etc/shadow")` or `C:\Windows\System32\config\SAM`. | Strict path jailing via `Path.resolve().is_relative_to(ALLOWED_ROOT)` plus sensitive substring blocklist (`.ssh`, `.env`, `id_rsa`). | `tests/test_bridge_security.py` |
| **Remote Code Execution (RCE) via Desktop Bridge** | Adversary attempts to format drives or establish persistent backdoors via `desktop_exec`. | Constant-time HMAC authentication (`X-Fleet-Key`), loopback binding (`127.0.0.1`), and regex blacklist (`format`, `diskpart`, `rmdir /s`, `rm -rf`). | `tests/test_bridge_security.py` |
| **Denial of Service (DoS) via Payload Flooding** | Attacker floods the bridge with gigabyte-sized JSON payloads. | Hard payload cap of 1MB enforced at HTTP handler entry. Payloads exceeding cap return `HTTP 413`. | `tests/test_bridge_security.py` |

---

## 3. The Five Concentric Rings of Defense

For operators deploying **Option C (Full Fleet Mesh & Remote Bridge)**:

```
           [ Internet / WAN ]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│ RING 1: Caddy TLS & Header Gatekeeper                  │
│ • Drops all traffic lacking valid 256-bit X-Fleet-Key  │
│ • Reverse-proxies only authenticated WebSocket streams │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 2: Loopback Isolation Interface                   │
│ • Desktop Bridge binds strictly to 127.0.0.1:8099      │
│ • No listening sockets open to LAN or WAN              │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 3: Constant-Time HMAC Bearer Authentication       │
│ • Authorization header validated with constant-time    │
│   hmac.compare_digest to eliminate timing attacks      │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 4: Hard Filesystem Jailing                        │
│ • Enforces target_path.is_relative_to(ALLOWED_ROOT)    │
│ • Blacklists .ssh, .env, id_rsa, id_ed25519, SAM hives │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 5: Sandboxed Shell Execution Policy               │
│ • Destructive regex patterns dropped with HTTP 403     │
│ • Enforces 30-second hard execution timeouts           │
└────────────────────────────────────────────────────────┘
```

---

## 4. Corporate Zscaler & Proxy Compliance

Corporate environments often employ Deep Packet Inspection (DPI) and strict egress firewalls:
- **WebSocket Frame Masking:** `wstunnel` encapsulates traffic within compliant RFC 6455 WebSocket frames over port 443.
- **TLS Handshake Parity:** Connections originate outbound from the enterprise client to the cloud VPS, appearing as standard secure web traffic to corporate security gateways.
- **Zero Local Privileges:** The client runs entirely in user-space without administrative or kernel privileges.

---

## 5. Reporting a Security Vulnerability

If you discover a vulnerability or security flaw in `hermes-fleet-memory`, please report it confidentially via GitHub Security Advisories or by emailing:

`amirulazw94@gmail.com`

We commit to acknowledging receipt within 24 hours and providing a remediation timeline.
