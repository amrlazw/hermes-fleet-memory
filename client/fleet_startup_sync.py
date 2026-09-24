#!/usr/bin/env python3
"""
Autonomous Fleet Ingress & On-Boot Task Dispatcher.

Reference implementation of a member node's boot-time worker. Run it on startup
or wake-from-sleep and it will:

1. Wait for network, then reach the control plane YOU deployed (FLEET_TASKS_URL).
2. Claim tasks queued for this node (FLEET_NODE_ID).
3. Optionally send a briefing over Telegram before work begins.
4. Execute the allowlisted action.
5. Post the completion receipt back to the task plane.
6. Optionally deliver a final execution ledger over Telegram.

Everything is environment-driven. There is no built-in hub address: if
FLEET_TASKS_URL is unset the script exits instead of contacting anyone.

Required:
  FLEET_TASKS_URL   Base URL of your own control plane, e.g. http://127.0.0.1:8088
  FLEET_KEY         Bearer token for that control plane
                    (FLEET_KEY_<NODEID> and FLEET_CLUSTER_SECRET are also honoured)

Optional:
  FLEET_NODE_ID     This node's name in the fleet (default: the machine hostname)
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   Enable Telegram briefings
  HERMES_HOME       Directory holding a .env to load (default: ~/.hermes)
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _load_env_files() -> None:
    """Load .env from HERMES_HOME and next to this script, never overriding real env."""
    try:
        import dotenv
    except Exception:
        return
    env_filename = ".env"
    for candidate in (
        os.path.join(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"), env_filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), env_filename),
    ):
        if os.path.exists(candidate):
            dotenv.load_dotenv(candidate, override=False)


_load_env_files()

NODE_ID = (
    os.getenv("FLEET_NODE_ID")
    or os.getenv("FLEET_CLIENT_ID")
    or socket.gethostname()
).strip().lower()

# Base URL only. A full ".../api/fleet/tasks" value is accepted for backwards
# compatibility and reduced back to its base.
_raw_url = os.getenv("FLEET_TASKS_URL", "").strip().rstrip("/")
if _raw_url.endswith("/api/fleet/tasks"):
    _raw_url = _raw_url[: -len("/api/fleet/tasks")]
FLEET_BASE = _raw_url
FLEET_API = f"{FLEET_BASE}/api/fleet/tasks" if FLEET_BASE else ""

FLEET_KEY = (
    os.getenv(f"FLEET_KEY_{NODE_ID.upper()}")
    or os.getenv("FLEET_KEY")
    or os.getenv("FLEET_CLUSTER_SECRET")
    or ""
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

if sys.platform == "win32":
    LOG_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\hermes\logs"))
else:
    LOG_DIR = Path(os.path.expanduser("~/.hermes/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "fleet_ingress_sync.log"

logging.basicConfig(
    level=logging.INFO,
    format=f"[%(asctime)s] [%(levelname)s] [{NODE_ID}-sync] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(f"{NODE_ID}-sync")

USER_AGENT = f"FleetIngress/{NODE_ID}"


def telegram_notify(text: str) -> bool:
    """Send a notification through the operator's own Telegram bot, if configured."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning("Telegram delivery failed: %s", e)
        return False


def wait_for_network(max_retries: int = 12, delay_s: int = 5) -> bool:
    """Poll our own control plane until the network adapter is up after boot/wake."""
    status_url = f"{FLEET_BASE}/api/fleet/status"
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(status_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    logger.info("Fleet connectivity confirmed on attempt %d.", attempt)
                    return True
        except Exception:
            logger.debug("Waiting for control plane (attempt %d/%d)...", attempt, max_retries)
            time.sleep(delay_s)
    return False


def fetch_pending_tasks() -> list[dict]:
    """Retrieve queued tasks assigned to this node."""
    req = urllib.request.Request(
        FLEET_API,
        headers={
            "Authorization": f"Bearer {FLEET_KEY}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tasks = data.get("tasks", [])
            # Filter tasks destined for this node and still pending
            return [
                t for t in tasks
                if t.get("target") == NODE_ID and t.get("status") in {"pending", "queued"}
            ]
    except Exception as e:
        logger.error("Failed to query fleet task plane: %s", e)
        return []


def claim_pending_task() -> dict | None:
    """Atomically claim the oldest pending task assigned to this node."""
    url = f"{FLEET_API}/pending?target={NODE_ID}&worker_id={NODE_ID}_worker"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {FLEET_KEY}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("task")
    except Exception as e:
        logger.warning("Failed to claim pending task: %s", e)
        return None


def complete_task(task_id: str, result: dict) -> bool:
    """Mark task as completed in the fleet plane."""
    url = f"{FLEET_API}/{task_id}/complete"
    payload = {"result": result}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {FLEET_KEY}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning("Failed to complete task %s: %s", task_id, e)
        return False


def execute_task(task: dict) -> dict:
    """Execute allowlisted task actions safely."""
    action = task.get("title") or task.get("action")
    directive = task.get("directive", "")
    logger.info("Executing task %s (%s): %s", task.get("id"), action, directive)

    if action == "fleet_health_ping":
        import platform
        return {
            "node": NODE_ID,
            "status": "online",
            "os": platform.platform(),
            "uptime_sync": time.time(),
        }

    if action in {"gpu_batch", "gpu_status_report"}:
        import subprocess
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=name,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                text=True,
                creationflags=creationflags,
            ).strip()
            name, temp, used, total = [x.strip() for x in out.splitlines()[0].split(",")]
            return {
                "node": NODE_ID,
                "gpu": name,
                "temp_c": int(temp),
                "vram_used_mb": int(used),
                "vram_total_mb": int(total),
                "status": "nominal",
            }
        except Exception as err:
            return {"node": NODE_ID, "error": str(err)}

    # Fallback acknowledgment
    return {
        "node": NODE_ID,
        "action": action,
        "status": "acknowledged",
        "detail": directive,
    }


def run_sync() -> int:
    if not FLEET_BASE:
        logger.error(
            "FLEET_TASKS_URL is not set, so there is no control plane to sync with. "
            "Point it at the hub you run yourself (e.g. http://127.0.0.1:8088) and "
            "re-run. This script never contacts a default or third-party hub."
        )
        return 2
    if not FLEET_KEY:
        logger.error(
            "No fleet bearer token found. Set FLEET_KEY (or FLEET_KEY_%s) in your "
            "environment or ~/.hermes/.env.", NODE_ID.upper()
        )
        return 2

    logger.info("Initiating autonomous fleet ingress sync for node '%s' -> %s", NODE_ID, FLEET_BASE)
    if not wait_for_network():
        logger.error("Control plane unreachable. Aborting sync.")
        return 1

    pending = fetch_pending_tasks()
    if not pending:
        logger.info("No pending tasks queued for '%s'. Node is ready and idle.", NODE_ID)
        return 0

    logger.info("Discovered %d pending task(s) for '%s'.", len(pending), NODE_ID)

    # 1. Briefing dispatched before execution begins
    briefing_lines = [
        f"*FLEET INGRESS BRIEFING - {NODE_ID.upper()}*",
        f"*Node:* `{NODE_ID}` | *Status:* `ONLINE`",
        f"*Pending Queue:* `{len(pending)} task(s) detected`",
        "",
        "*Incoming Tasks to Execute:*",
    ]
    for idx, t in enumerate(pending, 1):
        briefing_lines.append(f"{idx}. `{t.get('title', 'task')}`: {t.get('directive', 'No description')}")
    briefing_lines.append("")
    briefing_lines.append("_Commencing autonomous execution._")

    telegram_notify("\n".join(briefing_lines))

    # 2. Process tasks sequentially
    completed_reports = []
    while True:
        task = claim_pending_task()
        if not task:
            break

        task_id = task["task_id"]
        start_t = time.time()
        result = execute_task(task)
        duration_ms = round((time.time() - start_t) * 1000, 2)

        complete_task(task_id, result)
        completed_reports.append(
            f"*Task Completed:* `{task.get('title', 'task')}`\n"
            f"Duration: `{duration_ms} ms`\n"
            f"Output: ```json\n{json.dumps(result, indent=2)}\n```"
        )

    # 3. Post completion ledger
    if completed_reports:
        telegram_notify(
            f"*EXECUTION REPORT COMPLETE - {NODE_ID.upper()}*\n\n"
            + "\n\n".join(completed_reports)
            + "\n\n_All receipts recorded to the fleet task plane._"
        )
    logger.info("Fleet ingress sync completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run_sync())
