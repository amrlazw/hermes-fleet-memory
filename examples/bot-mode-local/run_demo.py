#!/usr/bin/env python3
"""Two sandboxed Hermes gateways talking to each other over `hermes peer`.

A local rehearsal of Fleet Memory nodes messaging each other directly, with no
human relaying. Nothing touches your real Hermes install:

* each node gets its own HERMES_HOME under --dir (default: your temp folder)
* each API server binds 127.0.0.1 on its own port (18642 / 18643)
* the sandbox agents have no shell, file, web, browser or messaging-platform
  tools, only Bot Mode's teammate messaging
* they borrow the `model:` block from your real config.yaml, so replies use
  whatever model your own Hermes uses

    python examples/bot-mode-local/run_demo.py           # set up, start, run both demos
    python examples/bot-mode-local/run_demo.py --demo    # re-run the demos on running gateways
    python examples/bot-mode-local/run_demo.py --stop    # stop the gateways, delete the sandbox
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NODES = {
    "chester": {
        "port": 18642,
        "title": "Chester",
        "role": "Fleet hub on the VPS. Runs the Telegram bot, the task plane and health checks.",
        "facts": "The task queue has two pending fleet_health_ping tasks, both for winston.",
    },
    "winston": {
        "port": 18643,
        "title": "Winston",
        "role": "Home GPU rig. Runs local inference and gpu_batch jobs.",
        "facts": "Your GPU is an RTX 3070 Ti, undervolted to 0.925 V at 1950 MHz. You are free after 22:00.",
    },
}

# Everything except teammate messaging. message_agent is injected into the
# canonical Bot Chat on its own, so it survives this list.
DISABLED_TOOLSETS = [
    "terminal", "file", "code_execution", "browser", "computer_use", "web", "search", "x_search",
    "delegation", "cronjob", "connections", "setup", "skills", "image_gen", "video_gen", "tts",
    "vision", "homeassistant", "spotify", "kanban", "project", "coding", "debugging", "discord",
    "discord_admin", "feishu_doc", "feishu_drive", "yuanbao", "desktop_ui", "memory", "clarify",
]

DEFAULT_DIR = Path(tempfile.gettempdir()) / "fleet-botmode-demo"


def hermes() -> str:
    path = shutil.which("hermes")
    if not path:
        sys.exit("hermes is not on PATH. Install Hermes Agent first.")
    return path


def with_api_key(block: str, env_var: str) -> str:
    """Swap the model's api_key for the value of env_var, so a key never goes on a command line."""
    key = os.environ.get(env_var, "")
    if not key:
        sys.exit(f"--api-key-env {env_var}: that environment variable is empty or unset.")
    line = f'  api_key: "{key}"'
    if re.search(r"^\s+api_key:", block, re.M):
        return re.sub(r"^\s+api_key:.*$", lambda _: line, block, flags=re.M)
    return block + line + "\n"


def real_model_block(config: Path | None) -> str:
    """The top-level `model:` block from a real config.yaml, copied verbatim."""
    if config is None:
        config = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "config.yaml"
    text = config.read_text(encoding="utf-8")
    match = re.search(r"^model:\n(?:[ \t].*\n|\n)+", text, re.M)
    if not match:
        sys.exit(f"No top-level model: block in {config}. Run `hermes model` first.")
    block = match.group(0).rstrip() + "\n"
    provider = re.search(r"^\s+provider:\s*\"?([\w.-]+)", block, re.M)
    print(f"  model from {config}: provider={provider.group(1) if provider else '?'}")
    return block


def write_node(root: Path, name: str, node: dict, model_block: str) -> dict:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    (home / "config.yaml").write_text(
        model_block
        + "agent:\n  bot_mode_protocol: true\n  disabled_toolsets:\n"
        + "".join(f"    - {t}\n" for t in DISABLED_TOOLSETS),
        encoding="utf-8")
    (home / ".env").write_text(
        "API_SERVER_ENABLED=true\n"
        f"API_SERVER_KEY={key}\n"
        "API_SERVER_HOST=127.0.0.1\n"
        f"API_SERVER_PORT={node['port']}\n",
        encoding="utf-8")
    # The ui_meta block is the marker that makes this a Bot-Mode-managed install,
    # which is what gives the canonical Bot Chat its message_agent tool.
    (home / "profile.yaml").write_text(
        f"description: {node['role']}\n"
        f"ui_meta:\n  hermes-bots:\n    title: {node['title']}\n",
        encoding="utf-8")
    (home / "SOUL.md").write_text(
        f"You are {node['title']}, a SANDBOX copy of a Fleet Memory node, running in a local demo.\n"
        f"Role: {node['role']}\n"
        f"What you know: {node['facts']}\n"
        "You have no tools except messaging your teammates. You cannot run commands or read files.\n"
        "Keep every reply to two or three plain sentences.\n",
        encoding="utf-8")
    return {"home": str(home), "port": node["port"], "key": key}


# The sandbox gets an allowlisted environment, never a copy of yours. Inheriting
# os.environ handed a real TELEGRAM_BOT_TOKEN to a sandbox gateway, which then
# started polling the real bot. Only what a process needs to run passes through.
_ENV_ALLOW = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "OS", "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS", "USERNAME", "USER", "LOGNAME", "COMPUTERNAME", "SHELL", "LANG",
    "LC_ALL", "TERM", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HERMES_GIT_BASH_PATH",
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
}

# Log lines that mean a gateway reached for a real messaging platform.
_PLATFORM_SIGNS = re.compile(r"\[(Telegram|Discord|Slack|WhatsApp|Signal|Matrix|Mattermost|Email)\]|"
                             r"(telegram|discord|slack|whatsapp|signal|matrix) (failed to )?connect", re.I)


def env_for(home: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOW}
    env.update(HERMES_HOME=home, PYTHONIOENCODING="utf-8")
    return env


def run(home: str, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([hermes(), *args], env=env_for(home), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start(root: Path, state: dict) -> None:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    for name, node in state["nodes"].items():
        if port_open(node["port"]):
            sys.exit(f"Port {node['port']} is already in use; stop whatever holds it or run --stop.")
        log = open(root / f"{name}.log", "w", encoding="utf-8")
        proc = subprocess.Popen([hermes(), "gateway", "run"], env=env_for(node["home"]),
                                stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        node["pid"] = proc.pid
        print(f"  started {name} gateway (pid {proc.pid}) -> 127.0.0.1:{node['port']}")
    save(root, state)
    deadline = time.time() + 120
    for name, node in state["nodes"].items():
        while not port_open(node["port"]):
            if time.time() > deadline:
                sys.exit(f"{name} did not open port {node['port']} within 120s; see {root / (name + '.log')}")
            time.sleep(1)
        print(f"  {name} API server is listening")
    time.sleep(5)
    for name in state["nodes"]:
        log = (root / f"{name}.log").read_text(encoding="utf-8", errors="replace")
        if _PLATFORM_SIGNS.search(log):
            stop(root)
            sys.exit(f"{name} tried to reach a real messaging platform. Stopped both sandboxes for safety.")
    print("  no messaging platforms started (api_server only)")


def register_peers(state: dict) -> None:
    nodes = state["nodes"]
    for name, node in nodes.items():
        for other, peer in nodes.items():
            if other == name:
                continue
            res = run(node["home"], "peer", "add", other,
                      "--url", f"http://127.0.0.1:{peer['port']}", "--key", peer["key"], timeout=60)
            status = "ok" if res.returncode == 0 else f"FAILED: {(res.stderr or res.stdout).strip()}"
            print(f"  {name}: peer {other} -> {status}")


def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def demo(state: dict) -> None:
    chester = state["nodes"]["chester"]["home"]

    banner("DEMO 1  chester -> winston, one direct message (hermes peer dm)")
    msg = ("Message from Chester (@chester): two fleet_health_ping tasks are queued for you. "
           "Are you able to take a gpu_batch tonight, and on which GPU?")
    print(f"chester sends:\n  {msg}\n")
    res = run(chester, "peer", "dm", "winston", msg)
    print("winston replies:\n  " + (res.stdout.strip() or res.stderr.strip()).replace("\n", "\n  "))

    banner("DEMO 2  chester's agent decides to ask winston itself (message_agent)")
    ask = ("Operator request: find out from Winston which GPU he has and when he is free tonight. "
           "Use message_agent to ask him, wait for his reply, then give me a one-line summary.")
    print(f"you tell chester:\n  {ask}\n")
    res = run(chester, "chat", "--continue", "Bot Chat", "--create-if-missing", "-q", ask, "--oneshot", "-Q")
    print("chester answers:\n  " + (res.stdout.strip() or res.stderr.strip()).replace("\n", "\n  "))


def save(root: Path, state: dict) -> None:
    (root / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def load(root: Path) -> dict:
    path = root / "state.json"
    if not path.exists():
        sys.exit(f"No demo at {root}. Run without flags first.")
    return json.loads(path.read_text(encoding="utf-8"))


def stop(root: Path) -> None:
    if (root / "state.json").exists():
        for name, node in load(root)["nodes"].items():
            pid = node.get("pid")
            if not pid:
                continue
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
            else:
                try:
                    os.killpg(pid, 15)
                except OSError:
                    pass
            print(f"  stopped {name} (pid {pid})")
    time.sleep(2)
    shutil.rmtree(root, ignore_errors=True)
    print(f"  removed {root}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help=f"sandbox location (default {DEFAULT_DIR})")
    ap.add_argument("--model-config", type=Path, default=None,
                    help="config.yaml whose model: block the sandboxes use (default: $HERMES_HOME/config.yaml)")
    ap.add_argument("--api-key-env", metavar="VAR",
                    help="use the value of this environment variable as the model's api_key")
    ap.add_argument("--demo", action="store_true", help="only re-run the demos against running gateways")
    ap.add_argument("--stop", action="store_true", help="stop the gateways and delete the sandbox")
    args = ap.parse_args()
    root = args.dir.resolve()

    if args.stop:
        stop(root)
        return 0
    if args.demo:
        demo(load(root))
        return 0

    if (root / "state.json").exists():
        sys.exit(f"A demo already exists at {root}. Use --demo to re-run it or --stop to remove it.")
    root.mkdir(parents=True, exist_ok=True)
    banner(f"Setting up two sandboxed Hermes nodes in {root}")
    model_block = real_model_block(args.model_config)
    if args.api_key_env:
        model_block = with_api_key(model_block, args.api_key_env)
    state = {"nodes": {name: write_node(root, name, node, model_block) for name, node in NODES.items()}}
    save(root, state)
    start(root, state)
    register_peers(state)
    demo(state)
    print("\nGateways are still running. Re-run the demos with --demo, clean up with --stop.")
    print(f"Logs: {root / 'chester.log'} and {root / 'winston.log'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
