#!/usr/bin/env python3
"""
hermes-fleet-memory: Hardened Desktop Execution & Blob Bridge (v2)
Zero-dependency, stdlib-only HTTP bridge allowing remote nodes to query telemetry,
execute safe allowlisted commands, download binary blobs, and archive directories with defense-in-depth security.
"""

import os
import sys
import re
import json
import hmac
import time
import shlex
import zipfile
import tempfile
import urllib.parse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Pure Python standard-library .env loader (zero external dependencies)
def load_env_file(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        val = v.strip().strip("'\"")
                        os.environ[k.strip()] = val
        except Exception:
            pass

candidate_envs = [
    os.path.expanduser("~/.hermes/.env"),
    os.path.expandvars(r"%LOCALAPPDATA%\hermes\profiles\winston\.env"),
    os.path.expanduser("~/.hermes/profiles/winston/.env"),
    os.path.join(os.path.dirname(__file__), ".env")
]
for env_p in candidate_envs:
    load_env_file(env_p)

PORT = int(os.getenv("FLEET_BRIDGE_PORT", "8099"))
HOST = "127.0.0.1"

# Decoupled bridge execution secret (distinct from Qdrant vector database key)
# Falls back to FLEET_QDRANT_KEY if FLEET_BRIDGE_KEY is unset
FLEET_BRIDGE_KEY = os.getenv("FLEET_BRIDGE_KEY") or os.getenv("FLEET_QDRANT_KEY") or ""

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

# Strict binary allowlist for shell=False execution
ALLOWED_BINARIES = {
    "nvidia-smi",
    "git",
    "ollama",
    "tasklist",
    "pgrep",
    "net",
    "uptime",
    "whoami",
    "python",
    "python3",
    "node"
}

# Pre-declared parameterized actions
ALLOWED_ACTIONS = {
    "gpu_status": ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
    "git_status": ["git", "status", "-s"],
    "git_log": ["git", "log", "-n", "5", "--oneline"],
    "ollama_ps": ["ollama", "ps"],
    "wstunnel_status": ["tasklist", "/FI", "IMAGENAME eq wstunnel.exe"] if sys.platform == "win32" else ["pgrep", "-l", "wstunnel"],
    "whoami": ["whoami"],
    "system_uptime": ["net", "statistics", "workstation"] if sys.platform == "win32" else ["uptime"],
    "threads_publish": ["python", "C:/Users/dontlookie/AppData/Local/hermes/bin/post_fleet_synapse_update.py", "--submit"]
}

# Parameterized argument blacklist
ARGUMENT_BLACKLIST = [
    r"^format(\.exe)?$",
    r"\bformat\s+[a-z]:",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"^rmdir(\.exe)?$",
    r"-[a-zA-Z]*r[a-zA-Z]*f",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"^reg(\.exe)?$",
    r"set-mppreference",
    r":\(\){\s*:\|:&\s*};:",
]


def parse_and_validate_command(cmd_str: str) -> list:
    """
    Safely tokenizes input string into a structured argument array for shell=False execution.
    Enforces binary allowlisting and parameter security rules.
    """
    try:
        tokens = shlex.split(cmd_str, posix=(sys.platform != "win32"))
    except ValueError as e:
        raise ValueError(f"Malformed command syntax: {e}")

    if not tokens:
        raise ValueError("Empty command provided")

    raw_bin = os.path.basename(tokens[0]).lower()
    binary = raw_bin[:-4] if raw_bin.endswith(".exe") else raw_bin

    if binary not in ALLOWED_BINARIES:
        raise PermissionError(
            f"Binary '{binary}' is not authorized. Bridge is locked to allowlist: {sorted(ALLOWED_BINARIES)}"
        )

    # Validate individual arguments against dangerous tokens
    for arg in tokens[1:]:
        arg_lower = arg.lower()
        for bad in ARGUMENT_BLACKLIST:
            if re.search(bad, arg_lower):
                raise PermissionError(f"Argument '{arg}' forbidden by security policy pattern: {bad}")

    return tokens


class SecureBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _verify_auth(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:].strip()
        current_key = FLEET_BRIDGE_KEY or os.getenv("FLEET_BRIDGE_KEY") or os.getenv("FLEET_QDRANT_KEY") or ""
        if not current_key:
            return False
        return hmac.compare_digest(token, current_key)

    def _stream_file(self, raw_path: str):
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
                self._send_json(403, {"error": f"Access denied: Path contains sensitive pattern '{blocked}'"})
                return

        if not target_path.exists():
            self._send_json(404, {"error": "File not found"})
            return

        if not target_path.is_file():
            self._send_json(400, {"error": "Path is not a regular file"})
            return

        file_size = target_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition", f'attachment; filename="{target_path.name}"')
        self.end_headers()

        with open(target_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except Exception:
                    break

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)

        if parsed_url.path in ["/health", "/status"]:
            gpu_data = {"name": "NVIDIA GPU", "temp_c": 0, "utilization_pct": 0, "mem_used_mb": 0, "mem_total_mb": 0}
            try:
                gpu_proc = subprocess.run(
                    ALLOWED_ACTIONS["gpu_status"],
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=5
                )
                if gpu_proc.returncode == 0 and gpu_proc.stdout.strip():
                    parts = [p.strip() for p in gpu_proc.stdout.strip().split(",")]
                    if len(parts) >= 5:
                        gpu_data["name"] = parts[0]
                        gpu_data["temp_c"] = int(parts[1]) if parts[1].isdigit() else 0
                        gpu_data["utilization_pct"] = int(parts[2]) if parts[2].isdigit() else 0
                        gpu_data["mem_used_mb"] = int(parts[3]) if parts[3].isdigit() else 0
                        gpu_data["mem_total_mb"] = int(parts[4]) if parts[4].isdigit() else 0
            except Exception:
                pass

            self._send_json(200, {
                "status": "online",
                "node": "Workstation",
                "os": sys.platform,
                "timestamp": time.time(),
                "gpu": gpu_data
            })
            return

        if parsed_url.path == "/download":
            if not self._verify_auth():
                self._send_json(401, {"error": "Unauthorized: Invalid or missing token"})
                return
            params = urllib.parse.parse_qs(parsed_url.query)
            raw_path = params.get("path", [""])[0].strip()
            self._stream_file(raw_path)
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if not self._verify_auth():
            self._send_json(401, {"error": "Unauthorized: Invalid or missing token"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            req_data = json.loads(body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if self.path == "/exec":
            action = req_data.get("action", "").strip()
            cmd_str = req_data.get("command", "").strip()

            tokens = None
            if action:
                if action not in ALLOWED_ACTIONS:
                    self._send_json(403, {
                        "error": f"Unknown action '{action}'. Pre-declared actions: {list(ALLOWED_ACTIONS.keys())}"
                    })
                    return
                tokens = ALLOWED_ACTIONS[action]
            elif cmd_str:
                try:
                    tokens = parse_and_validate_command(cmd_str)
                except (ValueError, PermissionError) as pe:
                    self._send_json(403, {"error": str(pe)})
                    return
            else:
                self._send_json(400, {"error": "Provide either 'action' or 'command'"})
                return

            try:
                proc = subprocess.run(
                    tokens,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                self._send_json(200, {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[:50000],
                    "stderr": proc.stderr[:50000]
                })
            except subprocess.TimeoutExpired:
                self._send_json(408, {"error": "Command timed out after 60 seconds"})
            except Exception as e:
                self._send_json(500, {"error": f"Execution error: {e}"})

        elif self.path == "/download":
            raw_path = req_data.get("path", "").strip()
            self._stream_file(raw_path)

        elif self.path == "/archive":
            raw_path = req_data.get("path", "").strip()
            if not raw_path:
                self._send_json(400, {"error": "No path provided"})
                return

            try:
                target_dir = Path(raw_path).resolve()
            except Exception as e:
                self._send_json(400, {"error": f"Invalid path resolution: {e}"})
                return

            try:
                target_dir.relative_to(ALLOWED_ROOT)
            except ValueError:
                self._send_json(403, {"error": f"Access denied: Path outside of {ALLOWED_ROOT}"})
                return

            path_str_lower = str(target_dir).lower()
            for blocked in BLOCKED_SUBSTRINGS:
                if blocked in path_str_lower:
                    self._send_json(403, {"error": f"Access denied: Path contains sensitive pattern '{blocked}'"})
                    return

            if not target_dir.exists() or not target_dir.is_dir():
                self._send_json(404, {"error": "Directory not found"})
                return

            try:
                tmp_zip = os.path.join(tempfile.gettempdir(), f"fleet_archive_{int(time.time())}_{target_dir.name}.zip")
                with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(target_dir):
                        for f in files:
                            full_p = os.path.join(root, f)
                            rel_p = os.path.relpath(full_p, target_dir)
                            zipf.write(full_p, rel_p)

                zip_size = os.path.getsize(tmp_zip)
                self._send_json(200, {
                    "status": "success",
                    "archive_path": tmp_zip,
                    "size_bytes": zip_size,
                    "download_url": f"/download?path={urllib.parse.quote(tmp_zip)}"
                })
            except Exception as e:
                self._send_json(500, {"error": f"Failed to create archive: {e}"})

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
                    self._send_json(403, {"error": f"Access denied: Path contains sensitive pattern '{blocked}'"})
                    return

            if not target_path.exists():
                self._send_json(404, {"error": "File not found"})
                return

            if not target_path.is_file():
                self._send_json(400, {"error": "Path is not a regular file"})
                return

            try:
                if target_path.stat().st_size > 5 * 1024 * 1024:
                    self._send_json(413, {"error": "File too large (max 5MB)"})
                    return

                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                self._send_json(200, {
                    "path": str(target_path),
                    "size_bytes": len(content.encode("utf-8")),
                    "content": content
                })
            except Exception as e:
                self._send_json(500, {"error": f"File read error: {e}"})

        elif self.path == "/power":
            action = req_data.get("action", "shutdown").lower().strip()
            delay = int(req_data.get("delay", 60))

            if action not in ["shutdown", "restart", "cancel"]:
                self._send_json(400, {"error": "Action must be 'shutdown', 'restart', or 'cancel'"})
                return

            try:
                if sys.platform == "win32":
                    if action == "shutdown":
                        cmd = ["shutdown.exe", "/s", "/t", str(delay), "/c", "Fleet Remote Shutdown Initiated"]
                    elif action == "restart":
                        cmd = ["shutdown.exe", "/r", "/t", str(delay), "/c", "Fleet Remote Restart Initiated"]
                    elif action == "cancel":
                        cmd = ["shutdown.exe", "/a"]
                else:
                    if action == "shutdown":
                        cmd = ["shutdown", f"+{delay // 60}", "Fleet Remote Shutdown"]
                    elif action == "restart":
                        cmd = ["shutdown", "-r", f"+{delay // 60}", "Fleet Remote Restart"]
                    elif action == "cancel":
                        cmd = ["shutdown", "-c"]

                proc = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=5)
                self._send_json(200, {
                    "action": action,
                    "delay_seconds": delay,
                    "exit_code": proc.returncode,
                    "output": proc.stdout or proc.stderr or "Command scheduled."
                })
            except Exception as e:
                self._send_json(500, {"error": f"Power action error: {e}"})

        else:
            self._send_json(404, {"error": "Not Found"})


def run_bridge():
    server = HTTPServer((HOST, PORT), SecureBridgeHandler)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Hardened Desktop Bridge v2 active on {HOST}:{PORT}")
    print(f"Allowed Root: {ALLOWED_ROOT}")
    print(f"Binary Allowlist: {sorted(ALLOWED_BINARIES)}")
    server.serve_forever()


if __name__ == "__main__":
    run_bridge()
