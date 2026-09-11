#!/usr/bin/env python3
"""
Hermes Fleet Memory — Universal Interactive Onboarding & Mesh Wizard
Guides developers step-by-step through node provisioning, cryptographic key generation,
reverse NAT tunneling, and MCP client integrations with zero guesswork.
"""

import os
import sys
import json
import secrets
import platform
import subprocess
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

def prompt_input(question: str, default: str = "") -> str:
    def_str = f" {DIM}(default: {default}){RESET}" if default else ""
    val = input(f"{BOLD}? {question}{def_str}: {RESET}").strip()
    return val if val else default

def prompt_yes_no(question: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    val = input(f"{BOLD}? {question} {DIM}{hint}{RESET}: ").strip().lower()
    if not val:
        return default
    return val in ["y", "yes"]

def run_autonomous_agent_setup(args):
    """
    Unattended headless execution path tailored for autonomous AI agents
    (Hermes, Claude Code, Codex, Devin, Cursor).
    Enforces deterministic validation, zero TTY hangs, and JSON verification receipts.
    """
    role = args.role or "standalone"
    receipt = {
        "status": "success",
        "role": role,
        "platform": platform.system().lower(),
        "artifacts_written": []
    }

    if role == "hub":
        secret = args.cluster_secret or secrets.token_hex(32)
        host = args.server_host or "127.0.0.1"
        env_content = f"""# Hermes Fleet Memory — Cloud Hub Configuration (Agent Provisioned)
FLEET_SERVER_HOST={host}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={secret}
FLEET_BRIDGE_KEY={secret}
FLEET_HARD_DOMAIN=all
"""
        env_path = Path("server/.env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(env_content, encoding="utf-8")
        receipt["artifacts_written"].append(str(env_path.resolve()))
        receipt["cluster_secret"] = secret
        receipt["deploy_method"] = args.deploy_method

    else:
        domain = args.domain or ("personal" if role == "desktop" else "work")
        client_id = args.client_id or ("winston" if role == "desktop" else "worker-node")
        secret = args.cluster_secret or secrets.token_hex(32)
        hub_url = args.hub_url or "wss://127.0.0.1:8443/tunnel"

        node_env = f"""# Hermes Fleet Memory — Member Node Configuration (Agent Provisioned)
FLEET_HARD_DOMAIN={domain}
FLEET_CLIENT_ID={client_id}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={secret}
FLEET_BRIDGE_KEY={secret}
FLEET_SERVER_HOST={hub_url.replace('wss://', '').replace('/tunnel', '')}
"""
        client_env = Path("client/.env")
        client_env.parent.mkdir(parents=True, exist_ok=True)
        client_env.write_text(node_env, encoding="utf-8")
        receipt["artifacts_written"].append(str(client_env.resolve()))
        receipt["domain_lock"] = domain
        receipt["client_id"] = client_id
        receipt["cluster_secret"] = secret

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
        print(f"     Secret: {receipt.get('cluster_secret')}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Hermes Fleet Memory Setup Wizard (Supports Interactive & Autonomous Agent Modes)"
    )
    parser.add_argument("--role", choices=["hub", "desktop", "edge", "standalone"], help="Node role in the fleet")
    parser.add_argument("--domain", choices=["personal", "work", "shared", "all"], help="Hardware domain firewall")
    parser.add_argument("--client-id", help="Unique identifier for this node (e.g. winston, laptop)")
    parser.add_argument("--hub-url", help="WebSocket ingress URL for Cloud Hub (e.g. wss://brain.example.com/tunnel)")
    parser.add_argument("--cluster-secret", help="256-bit cluster preshared secret")
    parser.add_argument("--server-host", help="Public domain or IP for Hub deployment")
    parser.add_argument("--deploy-method", choices=["docker", "systemd"], default="docker", help="Server deploy method")
    parser.add_argument("--non-interactive", action="store_true", help="Run unattended without interactive prompts (for AI agents)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON summary on completion")
    args = parser.parse_args()

    # Autonomous AI Agent Headless Mode
    if args.non_interactive or args.role:
        run_autonomous_agent_setup(args)
        return

    banner()

    print(f"{YELLOW}{BOLD}Architecture Sequence Rule:{RESET}")
    print(f"{DIM}1. [Hub] First deploy the Cloud Hub (Central Vector DB & WSTunnel Server).")
    print(f"2. [Nodes] Then connect Member Nodes (Home PC, Laptop) linking back to the Hub.{RESET}\n")
    print("─" * 65 + "\n")

    # Step 1: Topology Role
    role = prompt_choice(
        "What type of node are you setting up on this machine?",
        [
            ("hub", "Cloud Hub (Head / VPS / Central Qdrant + WSTunnel Server)"),
            ("desktop", "Personal Workstation Rig (GPU host with Desktop Execution Bridge)"),
            ("edge", "Worker / Laptop (Enterprise Work PC / Remote Client)"),
            ("standalone", "Local Demo Mode (Single-machine local Qdrant, zero tunnels)")
        ],
        default_idx=0
    )

    print(f"\n{GREEN}✔ Selected Role:{RESET} {BOLD}{role.upper()}{RESET}\n")

    # Flow A: Cloud Hub Setup
    if role == "hub":
        print(f"{CYAN}{BOLD}=== [Stage 1: Head Node Provisioning] ==={RESET}")
        cluster_secret = secrets.token_hex(32)
        print(f"Generated fresh 256-bit cluster secret:")
        print(f"  {GREEN}{BOLD}{cluster_secret}{RESET}\n")

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
FLEET_BRIDGE_KEY={cluster_secret}
FLEET_HARD_DOMAIN=all
"""
        env_path = Path("server/.env")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(env_content, encoding="utf-8")
        print(f"\n{GREEN}✔ Created server/.env with 256-bit cluster key.{RESET}")

        if deploy_method == "docker":
            print(f"\n{YELLOW}{BOLD}Next Steps for Docker Deployment:{RESET}")
            print(f"  1. Review Caddyfile: {CYAN}server/Caddyfile.example{RESET}")
            print(f"  2. Launch stack:    {BOLD}cd server && docker compose up -d{RESET}")
            print(f"  3. Check health:    {BOLD}curl http://127.0.0.1:6333/readyz{RESET}")
        else:
            print(f"\n{YELLOW}{BOLD}Next Steps for Native Systemd:{RESET}")
            print(f"  1. Copy units:      {BOLD}sudo cp server/systemd/*.service /etc/systemd/system/{RESET}")
            print(f"  2. Reload & start:  {BOLD}sudo systemctl daemon-reload && sudo systemctl enable --now qdrant wstunnel{RESET}")

        print(f"\n{MAGENTA}{BOLD}Node Join Credentials (Save this for your member nodes!):{RESET}")
        print(f"  Hub Endpoint:    {CYAN}wss://{domain_name}/tunnel{RESET}")
        print(f"  Cluster Secret:  {GREEN}{cluster_secret}{RESET}\n")
        return

    # Flow B: Member Node Setup (Desktop or Edge)
    print(f"{CYAN}{BOLD}=== [Stage 2: Member Node Attachment] ==={RESET}")
    hub_url = prompt_input("Enter your Hub WebSocket Ingress URL", "wss://brain.example.com/tunnel")
    cluster_secret = prompt_input("Enter the Hub 256-bit Cluster Secret (from Hub setup)")

    if not cluster_secret:
        cluster_secret = secrets.token_hex(32)
        print(f"{YELLOW}No secret entered. Generated standalone secret: {cluster_secret}{RESET}")

    domain = prompt_choice(
        "Choose the hardware domain isolation policy for this machine:",
        [
            ("personal", "personal  — Restricted to home rig / personal projects"),
            ("work", "work      — Restricted to corporate/enterprise data"),
            ("shared", "shared    — Standard collaborative developer workspace")
        ],
        default_idx=0 if role == "desktop" else 1
    )

    client_id = prompt_input("Enter unique Node ID (e.g. winston, laptop, work-pc)", "winston" if role == "desktop" else "work-pc")

    # Generate Node .env
    node_env = f"""# Hermes Fleet Memory — Member Node Configuration
FLEET_HARD_DOMAIN={domain}
FLEET_CLIENT_ID={client_id}
FLEET_QDRANT_HOST=127.0.0.1
FLEET_QDRANT_PORT=6333
FLEET_QDRANT_KEY={cluster_secret}
FLEET_BRIDGE_KEY={cluster_secret}
FLEET_SERVER_HOST={hub_url.replace('wss://', '').replace('/tunnel', '')}
"""
    client_env_path = Path("client/.env")
    client_env_path.parent.mkdir(parents=True, exist_ok=True)
    client_env_path.write_text(node_env, encoding="utf-8")
    print(f"\n{GREEN}✔ Generated client/.env with domain firewall [{domain}].{RESET}")

    # Desktop Bridge options for desktop role
    if role == "desktop":
        print(f"\n{CYAN}{BOLD}Desktop Execution Bridge Configuration:{RESET}")
        enable_bridge = prompt_yes_no("Enable Desktop Execution Bridge (:8099) on this machine?", True)
        if enable_bridge:
            print(f"  -> Bridge v2 will expose: telemetry, binary file downloads, folder zipping, and safe allowlisted commands.")

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

    if framework == "claude":
        claude_snippet = {
            "mcpServers": {
                "fleet-memory": {
                    "command": python_bin,
                    "args": [script_abs_path],
                    "env": {
                        "FLEET_HARD_DOMAIN": domain,
                        "FLEET_QDRANT_KEY": cluster_secret
                    }
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
      FLEET_HARD_DOMAIN: "{domain}"
      FLEET_QDRANT_KEY: "{cluster_secret}"
""")

    # OS-specific launcher assistance
    print(f"{CYAN}{BOLD}=== [Stage 4: Service Persistence] ==={RESET}")
    is_windows = platform.system().lower() == "windows"
    if is_windows:
        print(f"{BOLD}Windows Background Launchers Ready:{RESET}")
        print(f"  • Start tunnel & bridge silently at boot:")
        print(f"    Double-click or add to Startup: {CYAN}client\\start-tunnel.vbs{RESET}")
    else:
        print(f"{BOLD}Linux/macOS Background Launchers Ready:{RESET}")
        print(f"  • Start tunnel loop with auto-reconnect:")
        print(f"    {CYAN}bash client/start-tunnel.sh{RESET}")

    print("\n" + "═" * 65)
    print(f" {GREEN}{BOLD}🎉 NODE PROVISIONING COMPLETE!{RESET}")
    print(f" Test vector memory now:  {CYAN}python client/fleet_memory.py --test{RESET}")
    print("═" * 65 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Setup cancelled by user.{RESET}")
        sys.exit(0)
