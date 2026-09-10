#!/usr/bin/env python3
"""
hermes-fleet-memory: Desktop Execution Bridge
Lightweight, zero-dependency HTTP bridge allowing remote nodes to query telemetry,
execute safe shell commands, and read authorized files with defense-in-depth security.
"""

import os
import sys
import re
import json
import hmac
import time
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = int(os.getenv("FLEET_BRIDGE_PORT", "8099"))
HOST = "127.0.0.1"

# Shared cluster secret
FLEET_KEY = os.getenv("FLEET_QDRANT_KEY", "")

# Jailed directory for safe file retrieval (defaults to user home)
ALLOWED_ROOT = Path(os.getenv("FLEET_ALLOWED_ROOT", str(Path.home()))).resolve()

BLOCKED_SUBSTRINGS = [
    ".ssh",
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "sam",
    "system32",
    "shadow",
    "passwd",
]

COMMAND_BLACKLIST = [
    r"\bformat\s+[a-zA-Z]:",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"rmdir\s+/[sS]",
    r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+.*",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"\bnet\s+user\b",
    r"\breg\s+delete\b",
    r"set-mppreference",
    r":\(\){\s*:\|:&\s*};:",
]


class SecureBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard request logging
        pass

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _verify_auth(self) -> bool:
        if not FLEET_KEY:
            return False
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:].strip()
        return hmac.compare_digest(token, FLEET_KEY)

    def do_GET(self):
        if not self._verify_auth():
            self._send_json(401, {"error": "Unauthorized: Invalid or missing token"})
            return

        if self.path in ["/health", "/status"]:
            gpu_info = "N/A"
            try:
                gpu_proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if gpu_proc.returncode == 0:
                    parts = [p.strip() for p in gpu_proc.stdout.strip().split(",")]
                    if len(parts) >= 5:
                        gpu_info = {
                            "name": parts[0],
                            "temp_c": int(parts[1]),
                            "utilization_pct": int(parts[2]),
                            "mem_used_mb": int(parts[3]),
                            "mem_total_mb": int(parts[4])
                        }
            except Exception as e:
                gpu_info = f"GPU query error: {e}"

            self._send_json(200, {
                "status": "online",
                "node": os.getenv("FLEET_NODE_NAME", "Workstation"),
                "os": sys.platform,
                "timestamp": time.time(),
                "gpu": gpu_info
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if not self._verify_auth():
            self._send_json(401, {"error": "Unauthorized: Invalid or missing token"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 1024 * 1024:  # Max 1MB payload
            self._send_json(413, {"error": "Payload too large"})
            return

        body = self.rfile.read(content_length)
        try:
            req_data = json.loads(body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if self.path == "/exec":
            cmd = req_data.get("command", "").strip()
            if not cmd:
                self._send_json(400, {"error": "No command provided"})
                return

            cmd_lower = cmd.lower()
            for bad in COMMAND_BLACKLIST:
                if re.search(bad, cmd_lower):
                    self._send_json(403, {"error": f"Command forbidden by security policy pattern: {bad}"})
                    return

            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                stdout = proc.stdout[:50000]
                stderr = proc.stderr[:50000]
                self._send_json(200, {
                    "exit_code": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr
                })
            except subprocess.TimeoutExpired:
                self._send_json(408, {"error": "Command timed out after 30 seconds"})
            except Exception as e:
                self._send_json(500, {"error": f"Execution error: {e}"})

        elif self.path == "/read_file":
            raw_path = req_data.get("path", "").strip()
            if not raw_path:
                self._send_json(400, {"error": "No path provided"})
                return

            try:
                target_path = Path(raw_path).resolve()
            except Exception as e:
                self._send_json(400, {"error": f"Invalid path resolution: {e}"})
                return

            try:
                target_path.relative_to(ALLOWED_ROOT)
            except ValueError:
                self._send_json(403, {"error": f"Access denied: Path outside of {ALLOWED_ROOT}"})
                return

            path_str_lower = str(target_path).lower()
            for blocked in BLOCKED_SUBSTRINGS:
                if blocked in path_str_lower:
                    self._send_json(403, {"error": f"Access denied: Protected security file '{blocked}'"})
                    return

            if not target_path.is_file():
                self._send_json(404, {"error": "File not found or is a directory"})
                return

            if target_path.stat().st_size > 10 * 1024 * 1024:  # Max 10MB
                self._send_json(413, {"error": "File exceeds 10MB limit"})
                return

            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(500000)  # Max 500k chars inline
                self._send_json(200, {
                    "path": str(target_path),
                    "size_bytes": target_path.stat().st_size,
                    "content": content
                })
            except Exception as e:
                self._send_json(500, {"error": f"File read error: {e}"})

        elif self.path == "/power":
            action = req_data.get("action", "shutdown").lower().strip()
            delay = int(req_data.get("delay", 60))
            if delay < 0:
                delay = 0

            # Detect platform
            is_win = sys.platform == "win32"

            if action == "shutdown":
                if is_win:
                    cmd = f'shutdown.exe /s /t {delay} /c "Remote shutdown initiated via Hermes Fleet"'
                else:
                    cmd = f'shutdown -h +{max(1, delay // 60)} "Remote shutdown initiated via Hermes Fleet"'
                subprocess.Popen(cmd, shell=True)
                self._send_json(200, {
                    "status": "shutdown_initiated",
                    "action": "shutdown",
                    "delay_seconds": delay,
                    "message": f"System shutdown initiated. Power off in {delay}s. Use action='cancel' to abort."
                })
            elif action == "restart":
                if is_win:
                    cmd = f'shutdown.exe /r /t {delay} /c "Remote restart initiated via Hermes Fleet"'
                else:
                    cmd = f'shutdown -r +{max(1, delay // 60)} "Remote restart initiated via Hermes Fleet"'
                subprocess.Popen(cmd, shell=True)
                self._send_json(200, {
                    "status": "restart_initiated",
                    "action": "restart",
                    "delay_seconds": delay,
                    "message": f"System restart initiated. Reboot in {delay}s. Use action='cancel' to abort."
                })
            elif action in ("cancel", "abort"):
                cancel_cmd = "shutdown.exe /a" if is_win else "shutdown -c"
                res = subprocess.run(cancel_cmd, shell=True, capture_output=True, text=True)
                self._send_json(200, {
                    "status": "cancelled",
                    "message": "Scheduled shutdown or restart has been aborted successfully.",
                    "exit_code": res.returncode
                })
            else:
                self._send_json(400, {"error": "Invalid action. Supported: 'shutdown', 'restart', 'cancel'"})

        else:
            self._send_json(404, {"error": "Not Found"})


def run():
    server = HTTPServer((HOST, PORT), SecureBridgeHandler)
    print(f"Desktop Bridge active on http://{HOST}:{PORT} (Root: {ALLOWED_ROOT})")
    server.serve_forever()


if __name__ == "__main__":
    run()
