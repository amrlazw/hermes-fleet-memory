#!/usr/bin/env python3
"""
Hermes Fleet Memory — Universal Interactive Onboarding & Mesh Wizard
Guides developers step-by-step through node provisioning, cryptographic key generation,
reverse NAT tunneling, and MCP client integrations with zero guesswork.
"""

import json
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
WHITE = "\033[37m"

def banner():
    print(f"{CYAN}{BOLD}")
    print(r"""
  ██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗
  ██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝
  ███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗
  ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║
  ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║
  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝
      FLEET MEMORY & EXECUTION MESH WIZARD v2.0
    """)
    print(f"{RESET}{DIM}  Architecture: Paradigm E++  │  Zero Ambient Prompt Bloat{RESET}\n")

def prompt_choice(question: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    print(f"{BOLD}{WHITE}? {question}{RESET}")
    for idx, (val, desc) in enumerate(options):
        prefix = f"{GREEN}{BOLD}❯{RESET}" if idx == default_idx else " "
        print(f"  {prefix} {BOLD}[{idx + 1}]{RESET} {CYAN}{val:<16}{RESET} {DIM}— {desc}{RESET}")
    while True:
        choice = input(f"\n{BOLD}Select [1-{len(options)}] (default {default_idx + 1}): {RESET}").strip()
        if not choice:
            return options[default_idx][0]
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print(f"{RED}Invalid selection. Please choose between 1 and {len(options)}.{RESET}")

def hint(*lines: str) -> None:
    """Where to find the value the next prompt asks for."""
    for line in lines:
        print(f"  {DIM}↳ {line}{RESET}")


def prompt_input(question: str, default: str = "") -> str:
    def_str = f" {DIM}(default: {default}){RESET}" if default else ""
    val = input(f"{BOLD}? {question}{def_str}: {RESET}").strip()
    return val if val else default

def prompt_yes_no(question: str, default: bool = True) -> bool:
    yn = "[Y/n]" if default else "[y/N]"
    val = input(f"{BOLD}? {question} {yn}: {RESET}").strip().lower()
    if not val:
        return default
    return val in ["y", "yes"]


def send_setup_beacon(role: str, deploy_mode: str = "interactive"):
    """
    Sends an anonymous, non-blocking telemetry signal on wizard setup.
    Opt-in: nothing is sent unless FLEET_TELEMETRY=1, and DO_NOT_TRACK=1 always wins.
    """
    if os.getenv("FLEET_TELEMETRY") != "1" or os.getenv("DO_NOT_TRACK") == "1":
        return
    import threading

    def _ping():
        try:
            import hashlib
            import urllib.request
            raw_id = f"{platform.node()}_{platform.system()}_{platform.machine()}".encode("utf-8")
            instance_id = hashlib.sha256(raw_id).hexdigest()[:16]
            payload = json.dumps({
                "instance_id": instance_id,
                "arch_version": "2.0.0",
                "os_name": platform.platform(),
                "deploy_mode": f"{deploy_mode}_{role}"
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://fleet.republikus.my/api/telemetry/beacon",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "FleetMemory-Wizard/2.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass

    threading.Thread(target=_ping, daemon=True).start()

def scan_system_environment() -> dict:
    """
    Introspects host hardware, operating system, Docker daemon, GPUs, network interfaces,
    and existing AI agent configurations (Hermes, Claude Desktop, Cursor) to formulate
    an intelligent, tailored provisioning recommendation.
    """
    import shutil
    plat = platform.system().lower()

    # 1. Hardware & GPU Detection
    gpu_desc = None
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3
            ).stdout.strip()
            if out:
                gpu_desc = out.splitlines()[0]
        except Exception:
            pass

    # 2. Tooling / Daemons Detection
    has_docker = bool(shutil.which("docker"))
    has_wstunnel = bool(shutil.which("wstunnel") or shutil.which("wstunnel.exe"))

    # Check local hermes / AppData wstunnel
    if not has_wstunnel:
        candidate_wstunnels = [
            Path.home() / ".local/bin/wstunnel",
            Path(os.path.expandvars(r"%LOCALAPPDATA%\hermes\bin\wstunnel.exe"))
        ]
        has_wstunnel = any(p.exists() for p in candidate_wstunnels)

    # 3. Installed AI Frameworks
    installed_frameworks = []
    hermes_cfg = Path.home() / ".hermes/config.yaml"
    if hermes_cfg.exists():
        installed_frameworks.append("Hermes Agent")

    claude_cfgs = [
        Path.home() / ".config/Claude/claude_desktop_config.json",
        Path(os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json"))
    ]
    if any(p.exists() for p in claude_cfgs):
        installed_frameworks.append("Claude Desktop")

    cursor_cfgs = [
        Path.home() / ".cursor",
        Path(os.path.expandvars(r"%USERPROFILE%\.cursor"))
    ]
    if any(p.exists() for p in cursor_cfgs):
        installed_frameworks.append("Cursor")

    # 4. Synthesize Intelligent Recommendation
    recommended_role = "edge"
    recommended_sequence = "Member Node attachment linking back to Cloud Hub"

    if plat == "linux" and not gpu_desc:
        # Standard cloud VPS profile (Head node)
        recommended_role = "hub"
        recommended_sequence = "Head Node provisioning: Deploy Qdrant vector database + WSTunnel ingress server first."
    elif gpu_desc:
        # GPU Workstation rig
        recommended_role = "desktop"
        recommended_sequence = "Desktop Rig provisioning: Activate Desktop Bridge v2 + connect reverse WSTunnel to Hub."
    else:
        # Laptop / Client
        recommended_role = "edge"
        recommended_sequence = "Client / Edge Laptop provisioning: Lock domain to 'work' and wire FastMCP tool."

    return {
        "platform": plat,
        "os_version": platform.platform(),
        "python_version": platform.python_version(),
        "has_docker": has_docker,
        "has_wstunnel": has_wstunnel,
        "gpu_detected": gpu_desc,
        "installed_frameworks": installed_frameworks,
        "recommended_role": recommended_role,
        "recommended_sequence": recommended_sequence
    }

def run_autonomous_agent_setup(args):
    """
    Unattended headless execution path tailored for autonomous AI agents
    (Hermes, Claude Code, Codex, Devin, Cursor).
    Enforces deterministic validation, zero TTY hangs, and JSON verification receipts.
    """
    if args.scan:
        report = scan_system_environment()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"\n{CYAN}{BOLD}=== [System Pre-Flight Diagnostic Scan] ==={RESET}")
            print(f"OS Platform:          {BOLD}{report['platform']} ({report['os_version']}){RESET}")
            print(f"Python Environment:   {BOLD}{report['python_version']}{RESET}")
            print(f"Docker Engine:        {'[READY]' if report['has_docker'] else '[NOT FOUND]'}")
            print(f"WSTunnel Binary:      {'[READY]' if report['has_wstunnel'] else '[NOT FOUND]'}")
            print(f"GPU Hardware:         {report['gpu_detected'] or 'None / CPU-only'}")
            print(f"Installed AI Clients: {', '.join(report['installed_frameworks']) if report['installed_frameworks'] else 'None detected'}")
            print(f"\n{YELLOW}{BOLD}Recommended Role:{RESET}     {BOLD}{report['recommended_role'].upper()}{RESET}")
            print(f"{YELLOW}{BOLD}Recommended Sequence:{RESET} {report['recommended_sequence']}")
            print(f"\n{DIM}To apply this recommendation autonomously, run:{RESET}")
            print(f"  {CYAN}python setup.py --apply-plan --json{RESET}\n")
        return

    # If user/agent wants to auto-apply the recommendation
    if args.apply_plan:
        report = scan_system_environment()
        args.role = report["recommended_role"]
        args.domain = "personal" if args.role in ["desktop", "compute", "personal"] else ("work" if args.role in ["edge", "client", "work"] else "all")

    role = args.role or "standalone"
    if role in ["compute", "personal"]:
        role = "desktop"
    elif role in ["client", "work"]:
        role = "edge"

    receipt = {
        "status": "success",
        "role": role,
        "platform": platform.system().lower(),
        "artifacts_written": []
    }

    # Three separate secrets. Reusing one value for all of them meant a stolen
    # Qdrant key also opened the tunnel and the desktop bridge.
    bridge_key = args.bridge_key or secrets.token_hex(32)
    tunnel_key = args.tunnel_key or ""

    if role == "hub":
        secret = args.cluster_secret or secrets.token_hex(32)
        tunnel_key = tunnel_key or secrets.token_hex(32)
        host = args.server_host or "127.0.0.1"
        env_content = f"""# Hermes Fleet Memory — Head Node Configuration (Agent Provisioned)
FLEET_SERVER_HOST={host}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={secret}
FLEET_BRIDGE_KEY={bridge_key}
FLEET_TUNNEL_KEY={tunnel_key}
FLEET_HARD_DOMAIN=all
"""
        env_path = Path("server/.env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(env_content, encoding="utf-8")
        receipt["artifacts_written"].append(str(env_path.resolve()))
        receipt["cluster_secret"] = secret
        receipt["bridge_key"] = bridge_key
        receipt["tunnel_key"] = tunnel_key
        receipt["deploy_method"] = args.deploy_method

    else:
        domain = args.domain or ("personal" if role == "desktop" else "work")
        client_id = args.client_id or ("personal-node" if role == "desktop" else "work-node")
        secret = args.cluster_secret or secrets.token_hex(32)
        hub_url = args.hub_url or "wss://127.0.0.1:8443/tunnel"

        node_env = f"""# Hermes Fleet Memory — Member Node Configuration (Agent Provisioned)
FLEET_HARD_DOMAIN={domain}
FLEET_CLIENT_ID={client_id}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={secret}
FLEET_BRIDGE_KEY={bridge_key}
FLEET_SERVER_HOST={hub_url.replace('wss://', '').replace('/tunnel', '')}
"""
        if tunnel_key:
            node_env += f"FLEET_TUNNEL_KEY={tunnel_key}\n"
        client_env = Path("client/.env")
        client_env.parent.mkdir(parents=True, exist_ok=True)
        client_env.write_text(node_env, encoding="utf-8")
        receipt["artifacts_written"].append(str(client_env.resolve()))
        receipt["domain_lock"] = domain
        receipt["client_id"] = client_id
        receipt["cluster_secret"] = secret
        receipt["bridge_key"] = bridge_key
        if tunnel_key:
            receipt["tunnel_key"] = tunnel_key

    # FastMCP Hermes integration snippet
    script_abs_path = str((Path("client/fleet_memory.py")).resolve())
    receipt["fastmcp_config"] = {
        "mcpServers": {
            "fleet-memory": {
                "command": sys.executable,
                "args": [script_abs_path]
            }
        }
    }

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"[OK] Autonomous Provisioning Complete ({role.upper()})")
        print(f"     Artifacts: {receipt['artifacts_written']}")
        print(f"     Qdrant key: {receipt.get('cluster_secret')}")
        print(f"     Bridge key: {receipt.get('bridge_key')}")
        if receipt.get("tunnel_key"):
            print(f"     Tunnel key: {receipt.get('tunnel_key')}")

    send_setup_beacon(role=role, deploy_mode="autonomous_agent")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Hermes Fleet Memory Setup Wizard (Supports Interactive & Autonomous Agent Modes)"
    )
    parser.add_argument(
        "--role",
        choices=["hub", "personal", "work", "compute", "client", "desktop", "edge", "standalone"],
        help="Node role: 'hub' (Head Node/VPS), 'personal' (Personal PC/GPU Rig), 'work' (Work Laptop/Office PC), or 'standalone'"
    )
    parser.add_argument("--domain", choices=["personal", "work", "shared", "all"], help="Hardware domain firewall")
    parser.add_argument("--node-name", "--client-id", dest="client_id", help="Custom name for this node (e.g. brain-vps, rig-3070, work-laptop, macbook)")
    parser.add_argument("--hub-url", help="WebSocket ingress URL for Cloud Hub (e.g. wss://brain.example.com/tunnel)")
    parser.add_argument("--cluster-secret", help="256-bit cluster preshared secret (the Qdrant API key)")
    parser.add_argument("--bridge-key", help="Desktop bridge key, shared by the bridge host and the nodes that "
                        "call it. Generated if omitted.")
    parser.add_argument("--tunnel-key", help="X-Fleet-Key value Caddy checks on the hub tunnel. "
                        "Generated for the hub if omitted.")
    parser.add_argument("--server-host", help="Public domain or IP for Hub deployment")
    parser.add_argument("--deploy-method", choices=["docker", "systemd"], default="docker", help="Server deploy method")
    parser.add_argument("--non-interactive", action="store_true", help="Run unattended without interactive prompts (for AI agents)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON summary on completion")
    parser.add_argument("--scan", action="store_true", help="Perform non-invasive pre-flight environment scan and return architectural recommendation")
    parser.add_argument("--apply-plan", action="store_true", help="Autonomously execute the recommended architecture plan from scan")
    args = parser.parse_args()

    # Autonomous AI Agent Headless Mode
    if args.non_interactive or args.role or args.scan or args.apply_plan:
        run_autonomous_agent_setup(args)
        return

    banner()

    # Stage 0: Fleet Scale Assessment (How many nodes?)
    print(f"{CYAN}{BOLD}=== [Topology Discovery] ==={RESET}")
    fleet_size = prompt_choice(
        "How many computers / nodes do you want to link into your memory fleet?",
        [
            ("pair", "2 Nodes (Home PC + Work Laptop) — [Recommended: No VPS needed, $0 Qdrant Cloud]"),
            ("mesh", "3+ Nodes (Cloud VPS Hub + Home Rig + Work Laptop) — [Self-Hosted Power Mesh]"),
            ("standalone", "1 Machine Only (Standalone local testing / Single device memory)")
        ],
        default_idx=0
    )

    if fleet_size == "standalone":
        role = "standalone"
    elif fleet_size == "pair":
        print(f"\n{GREEN}✔ Selected:{RESET} {BOLD}2-Node Cloud Sync (No VPS needed){RESET}")
        print(f"{DIM}Tip: Uses Qdrant Cloud Free Tier (Permanent $0, 1GB RAM = ~500k memory vectors).")
        print(f"If you don't have one, grab your free URL & API Key in 60s at: https://cloud.qdrant.io/{RESET}\n")

        node_type = prompt_choice(
            "Which machine is THIS computer?",
            [
                ("personal", "Personal Machine (Home PC / Gaming Rig / Personal Mac)"),
                ("work", "Work Machine (Corporate Laptop / Office PC)")
            ],
            default_idx=0
        )
        role = "personal" if node_type == "personal" else "work"
    else:
        print(f"\n{YELLOW}{BOLD}Architecture Sequence Rule:{RESET}")
        print(f"{DIM}1. [Hub] First deploy the Cloud Hub (Central Vector DB & WSTunnel Server).")
        print(f"2. [Nodes] Then connect Member Nodes (Home PC, Laptop) linking back to the Hub.{RESET}\n")
        print("─" * 65 + "\n")

        role = prompt_choice(
            "What type of node are you setting up on this machine?",
            [
                ("hub", "Head Node (Central Cloud VPS / Qdrant Brain + WSTunnel Ingress)"),
                ("personal", "Personal Node (Home PC / Gaming Rig / GPU Host with Execution Bridge)"),
                ("work", "Work Node (Corporate Laptop / Office PC / Enterprise Client)")
            ],
            default_idx=0
        )

    # Normalize role alias
    if role in ["compute", "personal"]:
        role = "desktop"
    elif role in ["client", "work"]:
        role = "edge"

    print(f"\n{GREEN}✔ Target Node Role:{RESET} {BOLD}{role.upper()}{RESET}\n")

    # Flow A: Cloud Hub Setup
    if role == "hub":
        print(f"{CYAN}{BOLD}=== [Stage 1: Head Node Provisioning] ==={RESET}")
        cluster_secret = secrets.token_hex(32)
        bridge_key = secrets.token_hex(32)
        tunnel_key = secrets.token_hex(32)
        print("Generated three separate 256-bit secrets (Qdrant, tunnel, desktop bridge).\n")

        hint("A domain whose DNS A record points at this VPS (e.g. brain.example.com), or the VPS public IP.",
             "The public IP is on your cloud provider's instance page. Member nodes connect to wss://<this>/tunnel.")
        domain_name = prompt_input("Enter your Public Domain or VPS IP", "brain.example.com")
        deploy_method = prompt_choice(
            "How would you like to run the Hub services?",
            [
                ("docker", "Docker Compose (Recommended: Qdrant + WSTunnel + Caddy bundled)"),
                ("systemd", "Native Linux Systemd Services (Bare-metal setup)")
            ],
            default_idx=0
        )

        env_content = f"""# Hermes Fleet Memory — Cloud Hub Configuration
FLEET_SERVER_HOST={domain_name}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={cluster_secret}
FLEET_BRIDGE_KEY={bridge_key}
FLEET_TUNNEL_KEY={tunnel_key}
FLEET_HARD_DOMAIN=all
"""
        env_path = Path("server/.env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(env_content, encoding="utf-8")
        print(f"\n{GREEN}✔ Created server/.env with separate Qdrant, tunnel and bridge keys.{RESET}")

        if deploy_method == "docker":
            print(f"\n{YELLOW}{BOLD}Next Steps for Docker Deployment:{RESET}")
            print(f"  1. Review Caddyfile: {CYAN}server/Caddyfile.example{RESET} (X-Fleet-Key = tunnel key)")
            print(f"  2. Launch stack:    {BOLD}cd server && docker compose up -d{RESET}")
            print(f"  3. Check health:    {BOLD}curl http://127.0.0.1:6333/readyz{RESET}")
        else:
            print(f"\n{YELLOW}{BOLD}Next Steps for Native Systemd:{RESET}")
            print(f"  1. Copy units:      {BOLD}sudo cp server/systemd/*.service /etc/systemd/system/{RESET}")
            print(f"     Tunnel allowlist: {BOLD}sudo install -D -m 644 server/wstunnel-restrictions.yaml "
                  f"/etc/wstunnel/restrictions.yaml{RESET}")
            print(f"  2. Reload & start:  {BOLD}sudo systemctl daemon-reload && sudo systemctl enable --now qdrant wstunnel{RESET}")

        print(f"\n{MAGENTA}{BOLD}Node Join Credentials (Save this for your member nodes!):{RESET}")
        print(f"  Hub Endpoint:    {CYAN}wss://{domain_name}/tunnel{RESET}")
        print(f"  Qdrant Key:      {GREEN}{cluster_secret}{RESET}")
        print(f"  Tunnel Key:      {GREEN}{tunnel_key}{RESET}  (FLEET_TUNNEL_KEY, and X-Fleet-Key in the Caddyfile)")
        print(f"  Bridge Key:      {GREEN}{bridge_key}{RESET}  (FLEET_BRIDGE_KEY on the bridge workstation)\n")
        return

    # Flow B: Member Node Setup (Desktop or Edge)
    print(f"{CYAN}{BOLD}=== [Stage 2: Node Configuration] ==={RESET}")

    qdrant_url = ""
    tunnel_key = ""
    bridge_key = secrets.token_hex(32)
    if fleet_size == "pair":
        print(f"\n{CYAN}--- Configuring Managed Cloud Sync (Qdrant Cloud) ---{RESET}")
        hint("Sign in at https://cloud.qdrant.io and open your cluster (create a free 1GB one if you have none).",
             "Copy its endpoint URL from the cluster page. It ends in :6333.",
             "Your second machine uses the same URL and key.")
        qdrant_url = prompt_input("Enter your Qdrant Cloud URL (e.g. https://xxxx.cloud.qdrant.io:6333)", "https://xxxx.cloud.qdrant.io:6333")
        hint("Create one in the cluster's API Keys section. It is shown only once:",
             "if you did not save it, create a new key rather than searching for the old one.")
        cluster_secret = prompt_input("Enter your Qdrant Cloud API Key")
        hub_url = ""
    elif fleet_size == "standalone":
        # One machine: no hub, tunnel or bridge to join, so none of their keys are asked for.
        print(f"\n{CYAN}--- Configuring Local Memory (single machine) ---{RESET}")
        print(f"{DIM}Point this at a Qdrant running on this machine, or at a Qdrant Cloud cluster.{RESET}")
        hint("Qdrant running on this machine? Keep the default.",
             "No Qdrant yet? Keep the default; the Docker command to start one is shown at the end.",
             "Using Qdrant Cloud instead? Paste your cluster's endpoint URL from https://cloud.qdrant.io.")
        qdrant_url = prompt_input("Enter your Qdrant URL", "http://127.0.0.1:6333")
        hint("Only needed if you started Qdrant with QDRANT__SERVICE__API_KEY set, or for Qdrant Cloud",
             "(the cluster's API Keys section). A plain local Docker Qdrant has none: leave it blank.")
        cluster_secret = prompt_input("Enter your Qdrant API Key (blank if your local Qdrant has none)")
        hub_url = ""
    else:
        print(f"{DIM}Tip: the values below were printed under 'Node Join Credentials' at the end of hub setup.")
        print(f"Lost them? They are in server/.env on the hub:  grep -E 'QDRANT_KEY|TUNNEL_KEY|BRIDGE_KEY' server/.env{RESET}\n")
        hint("'Hub Endpoint' in the join credentials: wss://<your hub domain>/tunnel")
        hub_url = prompt_input("Enter your Hub WebSocket Ingress URL", "wss://brain.example.com/tunnel")
        hint("'Qdrant Key' in the join credentials, or FLEET_QDRANT_KEY in the hub's server/.env")
        cluster_secret = prompt_input("Enter the Hub Qdrant Key (from Hub setup)")
        hint("'Tunnel Key' in the join credentials, or FLEET_TUNNEL_KEY in the hub's server/.env.",
             "It is the X-Fleet-Key value in the hub's Caddyfile. Hubs set up before tunnel keys existed have",
             "none: leave it blank and the tunnel falls back to the Qdrant key, with a warning.")
        tunnel_key = prompt_input("Enter the Hub Tunnel Key (from Hub setup)")
        hint("'Bridge Key' in the join credentials, or FLEET_BRIDGE_KEY in the hub's server/.env.",
             "Leave it blank to generate one here, then set the same value on the hub.")
        bridge_key = prompt_input("Enter the Hub Bridge Key (from Hub setup, blank to generate one)")
        if not bridge_key:
            bridge_key = secrets.token_hex(32)
            print(f"{YELLOW}Generated bridge key: {bridge_key}")
            print(f"Set FLEET_BRIDGE_KEY to this value on the hub too, or desktop_* tools cannot authenticate.{RESET}")

    # A local Qdrant commonly runs without an API key; inventing one would only break auth.
    if not cluster_secret and fleet_size != "standalone":
        cluster_secret = secrets.token_hex(32)
        print(f"{YELLOW}No secret entered. Generated standalone secret: {cluster_secret}{RESET}")

    domain = prompt_choice(
        "Choose the hardware domain isolation policy for this machine:",
        [
            ("personal", "personal  — Restricted to home rig / personal projects"),
            ("work", "work      — Restricted to corporate/enterprise data"),
            ("shared", "shared    — Standard collaborative developer workspace")
        ],
        default_idx=0 if role in ("desktop", "standalone") else 1
    )

    client_id = prompt_input(
        "Give this node a custom name (e.g. brain-vps, my-rig, work-laptop, macbook)",
        "work-laptop" if role == "edge" else "personal-pc"
    )

    # Parse host/url for Qdrant Cloud vs Self-Hosted Hub
    if fleet_size in ("pair", "standalone") and qdrant_url.startswith("http"):
        clean_url = qdrant_url.replace("https://", "").replace("http://", "").rstrip("/")
        if ":" in clean_url:
            q_host, q_port = clean_url.split(":")
        else:
            q_host, q_port = clean_url, "6333"
        use_https = "true" if qdrant_url.startswith("https") else "false"
        title = ("Single-Machine Configuration" if fleet_size == "standalone"
                 else "2-Node Cloud Configuration (Qdrant Cloud)")
        node_env = f"""# Hermes Fleet Memory — {title}
FLEET_HARD_DOMAIN={domain}
FLEET_CLIENT_ID={client_id}
FLEET_QDRANT_HOST={q_host}
FLEET_QDRANT_PORT={q_port}
FLEET_QDRANT_HTTPS={use_https}
"""
        if cluster_secret:
            node_env += f"FLEET_QDRANT_KEY={cluster_secret}\n"
    else:
        node_env = f"""# Hermes Fleet Memory — Member Node Configuration
FLEET_HARD_DOMAIN={domain}
FLEET_CLIENT_ID={client_id}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={cluster_secret}
FLEET_BRIDGE_KEY={bridge_key}
FLEET_SERVER_HOST={hub_url.replace('wss://', '').replace('/tunnel', '')}
"""
        if tunnel_key:
            node_env += f"FLEET_TUNNEL_KEY={tunnel_key}\n"
    client_env_path = Path("client/.env")
    client_env_path.parent.mkdir(parents=True, exist_ok=True)
    client_env_path.write_text(node_env, encoding="utf-8")
    print(f"\n{GREEN}✔ Generated client/.env with domain firewall [{domain}].{RESET}")

    # Desktop Bridge options for desktop role
    if role == "desktop":
        print(f"\n{CYAN}{BOLD}Desktop Execution Bridge Configuration:{RESET}")
        enable_bridge = prompt_yes_no("Enable Desktop Execution Bridge (:8099) on this machine?", True)
        if enable_bridge:
            print("  -> Bridge v2 will expose: telemetry, binary file downloads, folder zipping, and safe allowlisted commands.")

    # MCP Client Selection
    print(f"\n{CYAN}{BOLD}=== [Stage 3: AI Framework Integration] ==={RESET}")
    framework = prompt_choice(
        "Which AI assistant framework would you like to configure?",
        [
            ("hermes", "Hermes Agent (Native FastMCP via ~/.hermes/config.yaml)"),
            ("claude", "Claude Desktop / Claude Code (claude_desktop_config.json)"),
            ("cursor", "Cursor / VS Code (.cursorrules or mcp.json)"),
            ("manual", "Skip auto-config (Display raw command snippet)")
        ],
        default_idx=0
    )

    script_abs_path = str((Path("client/fleet_memory.py")).resolve())
    python_bin = sys.executable

    mcp_env = {"FLEET_HARD_DOMAIN": domain}
    if cluster_secret:
        mcp_env["FLEET_QDRANT_KEY"] = cluster_secret

    if framework == "claude":
        claude_snippet = {
            "mcpServers": {
                "fleet-memory": {
                    "command": python_bin,
                    "args": [script_abs_path],
                    "env": mcp_env
                }
            }
        }
        print(f"\n{GREEN}✔ Claude Desktop Configuration Snippet:{RESET}")
        print(json.dumps(claude_snippet, indent=2))
        print(f"{DIM}Paste this into %APPDATA%\\Claude\\claude_desktop_config.json{RESET}")

    elif framework == "hermes":
        print(f"\n{GREEN}✔ Hermes Agent MCP Configuration:{RESET}")
        print(f"""Add the following under `mcp_servers:` in ~/.hermes/config.yaml:
  fleet-memory:
    command: {python_bin}
    args:
      - "{script_abs_path}"
    env:
""" + "".join(f'      {k}: "{v}"\n' for k, v in mcp_env.items()))

    # OS-specific launcher assistance
    if fleet_size == "standalone":
        print(f"{CYAN}{BOLD}=== [Stage 4: Local Memory] ==={RESET}")
        print(f"  • {GREEN}No hub, tunnel or bridge needed on a single machine.{RESET}")
        print("  • Qdrant must be running at the URL you entered. No Qdrant yet? With Docker:")
        print(f"    {CYAN}docker run -d -p 127.0.0.1:6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant{RESET}")
        print(f"  • Linking more machines later? Re-run {BOLD}python fleet_wizard.py{RESET} and choose 2 or 3+ nodes.")
    elif fleet_size == "pair":
        print(f"{CYAN}{BOLD}=== [Stage 4: Zero-DevOps Status] ==={RESET}")
        print(f"  • {GREEN}No local daemon or tunnel needed!{RESET}")
        print("  • Both machines connect directly to your encrypted Qdrant Cloud cluster.")
        print(f"  • When setting up your second machine, run {BOLD}python setup.py{RESET} and choose the same 2-node option.")
    else:
        print(f"{CYAN}{BOLD}=== [Stage 4: Service Persistence] ==={RESET}")
        is_windows = platform.system().lower() == "windows"
        if is_windows:
            print(f"{BOLD}Windows Background Launchers Ready:{RESET}")
            print("  • Start tunnel & bridge silently at boot:")
            print(f"    Double-click or add to Startup: {CYAN}client\\start-tunnel.vbs{RESET}")
        else:
            print(f"{BOLD}Linux/macOS Background Launchers Ready:{RESET}")
            print("  • Start tunnel loop with auto-reconnect:")
            print(f"    {CYAN}bash client/start-tunnel.sh{RESET}")

    print("\n" + "═" * 65)
    print(f" {GREEN}{BOLD}🎉 NODE PROVISIONING COMPLETE!{RESET}")
    print(f" Check this node now:     {CYAN}python client/fleet_memory.py --doctor{RESET}")
    print("═" * 65 + "\n")

    send_setup_beacon(role=role, deploy_mode="interactive")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Setup cancelled by user.{RESET}")
        sys.exit(0)
