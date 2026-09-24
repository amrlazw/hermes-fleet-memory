# Privacy Policy for Hermes Fleet Memory

**Last Updated:** September 24, 2026

Hermes Fleet Memory is a self-hosted, distributed vector memory and NAT-traversing execution mesh built for multi-instance Hermes AI agent fleets.

## 1. Zero Cloud Telemetry & Data Sovereignty
Hermes Fleet Memory operates under a strict **Zero Ambient Exfiltration** and **Local-First / Self-Hosted** paradigm:
- **No Third-Party Analytics:** We do not track, collect, or transmit any user prompt contents, memory embeddings, query strings, or personal identity metrics to external analytics providers.
- **Self-Hosted Infrastructure:** All episodic memories, vector points, and slot states reside exclusively within your self-hosted Qdrant instance and local files.
- **Hardware-Enforced Firewalls:** Sensitive partitions (`work`, `personal`, `shared`) are enforced at the OS and node level, preventing cross-domain information leakage.

## 2. Information Handled Locally
- **Vector Embeddings:** Generated locally or directed strictly to the operator's authorized Qdrant cluster endpoint.
- **Node Authorization:** Authentication uses constant-time cryptographic HMAC tokens and Ed25519 digital signatures verified entirely within your cluster.
- **Desktop Execution Bridge:** The optional local execution bridge listens strictly on local network interfaces and executes only pre-declared allowlisted binaries.

## 3. Network Communications
Any outbound or inter-node communications occur solely between endpoints configured explicitly by the server administrator (e.g. your private WSTunnel ingress or self-hosted control plane).

### Optional telemetry (off by default)
The only exception is an anonymous setup beacon that is **disabled unless you opt in** with
`FLEET_TELEMETRY=1`. When enabled, `--init` and the setup wizard send one request to the
maintainer's endpoint carrying an opaque 16-character instance hash, OS platform, version and
domain mode. It never carries memory contents, queries, file paths or credentials.
`DO_NOT_TRACK=1` disables it even when opted in.

## 4. Contact & Disclosures
For security audits, vulnerability reports, or inquiries regarding data handling, please submit an issue or security advisory via the official GitHub repository:
https://github.com/amrlazw/hermes-fleet-memory
