"""Delegate a task to a fleet node and verify the Ed25519 receipt.

Portable client - works from any machine that can reach the control plane.

    python client_delegate.py --message "deploy finished"
    python client_delegate.py --photo-url https://... --message "Gear 5"
    python client_delegate.py --action fleet_health_ping --target node-b

Auth resolution order:
    --key  ->  $FLEET_KEY  ->  $FLEET_HOME/auth.json  ->  ~/.hermes/fleet_auth.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify import fetch_jwks, verify_receipt  # noqa: E402

DEFAULT_AUTH_PATHS = [
    Path(os.getenv("FLEET_HOME", "")) / "auth.json" if os.getenv("FLEET_HOME") else None,
    Path.home() / ".hermes" / "fleet_auth.json",
]


def load_auth(explicit=None) -> dict:
    if explicit:
        return json.loads(Path(explicit).read_text(encoding="utf-8"))
    for candidate in DEFAULT_AUTH_PATHS:
        if candidate and candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if data.get("fleet_key"):
                return data
    return {}


def post(url, token, payload, timeout=15):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"error": body}


def get(url, token, timeout=15):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode("utf-8", "replace")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Delegate a fleet task")
    ap.add_argument("--url", default=os.getenv("FLEET_URL", "http://127.0.0.1:8088"),
                    help="control plane base URL")
    ap.add_argument("--key", default=os.getenv("FLEET_KEY", ""), help="bearer token")
    ap.add_argument("--auth", default=None, help="path to an auth JSON file")
    ap.add_argument("--target", default=None, help="target node (default: first configured)")
    ap.add_argument("--action", default="telegram_notify",
                    choices=["telegram_notify", "fleet_health_ping", "gpu_batch"])
    ap.add_argument("--message", default="", help="message text / caption")
    ap.add_argument("--photo-url", default=None, help="image URL for telegram_notify")
    ap.add_argument("--priority", default="normal", choices=["low", "normal", "critical"])
    ap.add_argument("--timeout", type=int, default=60, help="seconds to wait for completion")
    args = ap.parse_args(argv)

    auth = load_auth(args.auth)
    base = args.url or auth.get("fleet_endpoint", "http://127.0.0.1:8088")
    base = base.rstrip("/")
    if not base.startswith("http"):
        base = "http://" + base
    token = args.key or auth.get("fleet_key", "")

    if not token:
        print("[x] No bearer token. Pass --key, set $FLEET_KEY, or create "
              "~/.hermes/fleet_auth.json with {\"fleet_key\": \"...\"}.", file=sys.stderr)
        return 2

    params = {}
    if args.message:
        params["message"] = args.message
    if args.photo_url:
        params["photo_url"] = args.photo_url

    payload = {
        "action": args.action,
        "priority": args.priority,
        "params": params,
        "idempotency_key": f"cli_{uuid.uuid4().hex}",
    }
    if args.target:
        payload["target"] = args.target

    if not payload.get("target"):
        _, health = get(f"{base}/healthz", token)
        nodes = health.get("nodes") or []
        if not nodes:
            print(f"[x] Could not determine target node: {health}", file=sys.stderr)
            return 1
        payload["target"] = nodes[0]

    status, body = post(f"{base}/api/fleet/tasks", token, payload)
    if status not in (200, 202):
        print(f"[x] Submit failed (HTTP {status}): {body}", file=sys.stderr)
        return 1

    task_id = body["task_id"]
    print(f"[+] {body['status']}: {task_id} -> {body['target']} ({payload['action']})")

    deadline = time.time() + args.timeout
    record = {}
    while time.time() < deadline:
        _, record = get(f"{base}/api/fleet/tasks/{task_id}", token)
        if record.get("status") in ("completed", "failed", "dead_letter"):
            break
        time.sleep(1)

    final = record.get("status", "timeout")
    print(f"[=] status: {final}")
    if record.get("result"):
        print(f"    result: {json.dumps(record['result'])}")
    if record.get("error"):
        print(f"    error : {record['error']}")

    if final == "completed":
        try:
            verified = verify_receipt(record, fetch_jwks(base))
            print(f"[*] receipt signature: {'VERIFIED' if verified else 'INVALID'} "
                  f"(kid={record.get('kid')})")
            return 0 if verified else 1
        except Exception as exc:  # noqa: BLE001
            print(f"[!] could not verify receipt: {exc}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
