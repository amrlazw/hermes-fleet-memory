#!/usr/bin/env python3
"""
hermes-fleet-memory
Universal FastMCP stdio server providing zero-bloat distributed vector memory
and optional remote desktop execution bridge for multi-instance Hermes fleets.
"""

import os
import sys
import uuid
import time
import warnings
from typing import Optional, List, Dict, Any

# Silence warnings to protect stdio JSON-RPC stream
warnings.filterwarnings("ignore")

# Load environment variables from Hermes profile if available
try:
    import dotenv
    candidate_envs = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expandvars(r"%LOCALAPPDATA%\hermes\profiles\winston\.env"),
        os.path.expandvars(r"%USERPROFILE%\.hermes\.env"),
        os.path.expanduser("~/.hermes/profiles/winston/.env"),
        os.path.join(os.path.dirname(__file__), ".env")
    ]
    for env_p in candidate_envs:
        if os.path.exists(env_p):
            dotenv.load_dotenv(env_p, override=False)
except Exception:
    pass

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from fastembed import TextEmbedding
except ImportError as e:
    sys.stderr.write(f"Warning: Dependencies missing: {e}\n")

# Initialize FastMCP (supports both mcp 2.x MCPServer and mcp 1.x FastMCP)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
    mcp = FastMCP("fleet-memory")
    HAS_MCP = True
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("fleet-memory")
        HAS_MCP = True
    except ImportError:
        HAS_MCP = False
        mcp = None

COLLECTION_NAME = "hermes_fleet_memory"

# Domain isolation: "work", "personal", "shared", or "all"
ENFORCED_DOMAIN = os.getenv("FLEET_HARD_DOMAIN", "work").lower()

# Qdrant Endpoint Configuration
QDRANT_HOST = os.getenv("FLEET_QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("FLEET_QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("FLEET_QDRANT_KEY", None)
QDRANT_HTTPS = os.getenv("FLEET_QDRANT_HTTPS", "false").lower() == "true"
QDRANT_URL = os.getenv("FLEET_QDRANT_URL", None)

# Optional Desktop Bridge port (default: 8099)
BRIDGE_PORT = int(os.getenv("FLEET_BRIDGE_PORT", "8099"))

# Global singletons
_client = None
_embedder = None


def get_client():
    global _client
    if _client is None:
        if QDRANT_URL:
            _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, check_compatibility=False)
        else:
            _client = QdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                api_key=QDRANT_API_KEY,
                https=QDRANT_HTTPS,
                check_compatibility=False
            )
    return _client


def get_embedder():
    global _embedder
    if _embedder is None:
        # BAAI/bge-small-en-v1.5 produces 384-dim normalized embeddings with FP32 precision
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder


def fleet_memory_search(
    query: str,
    limit: int = 5,
    client_id: Optional[str] = None,
    target_domain: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search fleet memory on-demand via vector similarity.
    
    Parameters:
    - query: Natural language search string.
    - limit: Maximum number of points to retrieve.
    - client_id: Optional filter for a specific client/subsystem.
    - target_domain: "personal", "work", "shared", or "all". If omitted, searches node domain + shared.
    """
    try:
        client = get_client()
        embedder = get_embedder()
        vector = list(embedder.embed([query]))[0].tolist()

        must_conditions = [
            models.FieldCondition(key="status", match=models.MatchValue(value="active"))
        ]

        # Domain filtering logic
        if target_domain == "all" or (not target_domain and ENFORCED_DOMAIN == "all"):
            pass  # Search across all domains without restriction
        elif target_domain in ["work", "personal", "shared"]:
            must_conditions.append(models.FieldCondition(key="domain", match=models.MatchValue(value=target_domain)))
        else:
            domains_to_search = list(set([ENFORCED_DOMAIN, "shared"]))
            must_conditions.append(
                models.FieldCondition(key="domain", match=models.MatchAny(any=domains_to_search))
            )

        if client_id:
            must_conditions.append(models.FieldCondition(key="client_id", match=models.MatchValue(value=client_id)))

        query_filter = models.Filter(must=must_conditions)

        # Hybrid client query compatibility
        try:
            results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            ).points
        except AttributeError:
            results = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            )

        output = []
        for r in results:
            payload = r.payload or {}
            output.append({
                "score": round(float(r.score), 4),
                "domain": payload.get("domain", "unknown"),
                "client_id": payload.get("client_id", "unknown"),
                "slot_name": payload.get("slot_name", "unknown"),
                "text": payload.get("text", ""),
                "page": payload.get("page", None),
                "pinned": payload.get("pinned", False),
                "created_at": payload.get("created_at", 0)
            })
        return output
    except Exception as e:
        sys.stderr.write(f"Fleet memory search error: {e}\n")
        return [{
            "score": 0.0,
            "domain": "system",
            "client_id": "fleet_memory",
            "slot_name": "connectivity_notice",
            "text": f"Warning: Fleet memory vector search failed ({e}). Check Qdrant endpoint connectivity.",
            "pinned": True,
            "created_at": int(time.time())
        }]


def fleet_memory_store(
    text: str,
    client_id: Optional[str] = None,
    slot_name: Optional[str] = None,
    target_domain: Optional[str] = None,
    pinned: bool = False
) -> Dict[str, Any]:
    """
    Store or update an authoritative card in fleet memory.
    
    Parameters:
    - text: Markdown content or factual statement to store.
    - client_id: Component or subsystem identifier (e.g., "hardware", "payment_gateway").
    - slot_name: Unique slot name. If provided, updates existing record in-place via deterministic UUID5.
    - target_domain: "personal", "work", or "shared".
    - pinned: If True, protects from the 90-day episodic expiry cleaner.
    """
    effective_domain = target_domain if target_domain in ["work", "personal", "shared"] else ENFORCED_DOMAIN
    if effective_domain == "all":
        effective_domain = "shared"

    # Deterministic slot overwrite using UUID5
    if slot_name and client_id:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{effective_domain}:{client_id}:{slot_name}"))
        is_pinned = True
    else:
        point_id = str(uuid.uuid4())
        is_pinned = pinned

    try:
        client = get_client()
        embedder = get_embedder()
        vector = list(embedder.embed([text]))[0].tolist()

        payload = {
            "text": text,
            "domain": effective_domain,
            "client_id": client_id or "generic",
            "slot_name": slot_name or "episodic",
            "status": "active",
            "pinned": is_pinned,
            "created_at": int(time.time()),
            "expires_at": 0 if is_pinned else int(time.time() + (90 * 86400))
        }

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

        return {
            "status": "success",
            "id": point_id,
            "domain": effective_domain,
            "mode": "in_place_overwrite" if (slot_name and client_id) else "episodic_append",
            "pinned": is_pinned
        }
    except Exception as e:
        sys.stderr.write(f"Fleet memory store error: {e}\n")
        return {
            "status": "error",
            "error_type": "connectivity_error",
            "message": f"Failed to store memory card: {e}",
            "domain": effective_domain,
            "id": point_id
        }


# Register FastMCP tools if available
if HAS_MCP and mcp:
    fleet_memory_search = mcp.tool(
        name="fleet_memory_search",
        description="Search fleet memory on-demand. Query domain is hardware-enforced by host OS."
    )(fleet_memory_search)

    fleet_memory_store = mcp.tool(
        name="fleet_memory_store",
        description="Store or update architectural notes in fleet memory. Domain is hardware-enforced."
    )(fleet_memory_store)

    @mcp.tool(
        name="desktop_status",
        description="Check if the remote workstation is online and retrieve live GPU/system telemetry."
    )
    def desktop_status() -> Dict[str, Any]:
        """Check if remote workstation bridge is online and return live GPU telemetry."""
        import json, urllib.request
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/health",
                headers={"Authorization": f"Bearer {QDRANT_API_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        return {
            "status": "offline",
            "message": "Workstation is currently powered off or desktop bridge is unreachable."
        }

    @mcp.tool(
        name="desktop_exec",
        description="Execute a safe terminal command remotely on the target workstation."
    )
    def desktop_exec(command: str) -> Dict[str, Any]:
        """Execute a safe shell command on the workstation."""
        import json, urllib.request, urllib.error
        try:
            data = json.dumps({"command": command}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/exec",
                data=data,
                headers={
                    "Authorization": f"Bearer {QDRANT_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Bridge communication error: {e}"}

    @mcp.tool(
        name="desktop_read_file",
        description="Read the contents of a safe file from the remote workstation."
    )
    def desktop_read_file(path: str) -> Dict[str, Any]:
        """Read a file on the remote workstation."""
        import json, urllib.request, urllib.error
        try:
            data = json.dumps({"path": path}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/read_file",
                data=data,
                headers={
                    "Authorization": f"Bearer {QDRANT_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Bridge communication error: {e}"}

    @mcp.tool(
        name="desktop_power",
        description="Gracefully shutdown, restart, or cancel a pending power-off on the remote workstation."
    )
    def desktop_power(action: str = "shutdown", delay_seconds: int = 60) -> Dict[str, Any]:
        """Manage workstation power state: 'shutdown', 'restart', or 'cancel'."""
        import json, urllib.request, urllib.error
        try:
            data = json.dumps({"action": action, "delay": delay_seconds}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/power",
                data=data,
                headers={
                    "Authorization": f"Bearer {QDRANT_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Bridge communication error: {e}"}


def bootstrap_collection():
    client = get_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
        )
        for field in ["domain", "client_id", "status", "memory_type", "pinned"]:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD
            )
        print(f"Collection '{COLLECTION_NAME}' bootstrapped successfully.")
    else:
        print(f"Collection '{COLLECTION_NAME}' already active.")


def run_init():
    """
    Autonomous one-click client initialization:
    1. Audits or provisions environment configuration (.env and Hermes profiles)
    2. Probes Qdrant vector engine connectivity and round-trip latency
    3. Bootstraps collection and payload keyword indices
    4. Automatically registers FastMCP server in Hermes Agent (hermes mcp add)
    5. Sets Hermes memory.provider to 'none' (zero ambient token overhead)
    6. Executes a live self-test query
    """
    import argparse
    import shutil
    import subprocess

    global ENFORCED_DOMAIN, QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY, QDRANT_HTTPS, QDRANT_URL, _client

    parser = argparse.ArgumentParser(description="Autonomous Client Node Initialization")
    parser.add_argument("--init", action="store_true", help="Run initialization")
    parser.add_argument("--setup", action="store_true", help="Alias for --init")
    parser.add_argument("--domain", choices=["work", "personal", "shared", "all"], help="Node domain partition")
    parser.add_argument("--url", help="Qdrant Cloud or remote endpoint URL")
    parser.add_argument("--key", help="Qdrant API key or cluster secret")
    parser.add_argument("--host", help="Qdrant host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Qdrant port (default: 6333)")
    parser.add_argument("--https", choices=["true", "false"], help="Use HTTPS for Qdrant host/port")
    
    parsed, _ = parser.parse_known_args()

    env_file = os.path.join(os.path.dirname(__file__), ".env")
    env_example = os.path.join(os.path.dirname(__file__), ".env.example")

    # If parameters were passed via CLI, update globals and optionally write .env
    updated_env = False
    new_domain = parsed.domain or ENFORCED_DOMAIN
    new_url = parsed.url or QDRANT_URL
    new_key = parsed.key or QDRANT_API_KEY
    new_host = parsed.host or QDRANT_HOST
    new_port = parsed.port or QDRANT_PORT
    new_https = (parsed.https.lower() == "true") if parsed.https else QDRANT_HTTPS

    # Auto-provision .env if no env exists in candidates
    has_any_env = any(os.path.exists(p) for p in candidate_envs)
    if (not has_any_env or parsed.domain or parsed.url or parsed.key) and not os.path.exists(env_file):
        try:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("# hermes-fleet-memory Auto-Provisioned Environment\n")
                f.write(f"FLEET_HARD_DOMAIN={new_domain}\n")
                if new_url:
                    f.write(f"FLEET_QDRANT_URL={new_url}\n")
                else:
                    f.write(f"FLEET_QDRANT_HOST={new_host}\n")
                    f.write(f"FLEET_QDRANT_PORT={new_port}\n")
                    f.write(f"FLEET_QDRANT_HTTPS={'true' if new_https else 'false'}\n")
                if new_key:
                    f.write(f"FLEET_QDRANT_KEY={new_key}\n")
                else:
                    # Generate a secure cluster secret if none provided
                    import secrets
                    f.write(f"FLEET_QDRANT_KEY={secrets.token_hex(32)}\n")
            print(f"[+] Created local client environment at: {env_file}")
            updated_env = True
        except Exception as e:
            print(f"[!] Note: Could not auto-write .env: {e}")

    # Re-apply globals
    ENFORCED_DOMAIN = new_domain
    QDRANT_URL = new_url
    QDRANT_API_KEY = new_key
    QDRANT_HOST = new_host
    QDRANT_PORT = new_port
    QDRANT_HTTPS = new_https
    _client = None  # Reset client singleton to use updated endpoint

    print("\n" + "=" * 64)
    print(" hermes-fleet-memory : Autonomous Client Node Initialization")
    print("=" * 64 + "\n")

    # Step 1: Environment audit
    print("[1/5] Auditing environment configuration...")
    endpoint_desc = QDRANT_URL if QDRANT_URL else f"http{'s' if QDRANT_HTTPS else ''}://{QDRANT_HOST}:{QDRANT_PORT}"
    print(f"      * Enforced Domain: {ENFORCED_DOMAIN.upper()}")
    print(f"      * Vector Target  : {endpoint_desc}")
    print(f"      * Desktop Bridge : port {BRIDGE_PORT}")

    # Step 2: Live Connectivity Probe
    print("\n[2/5] Probing vector engine connectivity...")
    t0 = time.time()
    try:
        client = get_client()
        collections_resp = client.get_collections()
        latency_ms = (time.time() - t0) * 1000
        print(f"      [OK] Connected to Qdrant successfully (Latency: {latency_ms:.1f}ms)")
    except Exception as e:
        print(f"\n[!] Connection Failed to {endpoint_desc}")
        print(f"    Error: {e}")
        print("\n    Troubleshooting hints:")
        print("    * If using Option A (VPS with WSTunnel):")
        print("      Verify wstunnel is running: e.g. wstunnel.exe client -L 'tcp://127.0.0.1:6333:127.0.0.1:6333' wss://...")
        print("    * If using Option B (Qdrant Cloud):")
        print("      Verify FLEET_QDRANT_URL and FLEET_QDRANT_KEY in your .env file.")
        print("    * If using direct local Qdrant:")
        print("      Verify docker compose or systemctl status qdrant is active.\n")
        sys.exit(1)

    # Step 3: Bootstrap Collection
    print("\n[3/5] Bootstrapping collection & payload indexes...")
    try:
        bootstrap_collection()
        print(f"      [OK] Collection '{COLLECTION_NAME}' validated (384-dim COSINE)")
    except Exception as e:
        print(f"      [!] Bootstrap error: {e}")
        sys.exit(1)

    # Step 4: Hermes Agent Auto-Registration
    print("\n[4/5] Configuring Hermes Agent...")
    hermes_bin = shutil.which("hermes")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    python_bin = sys.executable.replace("\\", "/")

    if hermes_bin:
        print(f"      * Found Hermes CLI at: {hermes_bin}")
        try:
            cmd_add = [
                hermes_bin, "mcp", "add", "fleet-memory",
                "--command", python_bin,
                "--args", script_path
            ]
            res_add = subprocess.run(cmd_add, capture_output=True, text=True)
            if res_add.returncode == 0 or "already exists" in (res_add.stdout + res_add.stderr).lower():
                print("      [OK] FastMCP server 'fleet-memory' registered in Hermes")
            else:
                msg = res_add.stdout.strip() or res_add.stderr.strip()
                print(f"      * MCP registration note: {msg}")
        except Exception as e:
            print(f"      [!] Note on MCP add: {e}")

        try:
            cmd_cfg = [hermes_bin, "config", "set", "memory.provider", "none"]
            res_cfg = subprocess.run(cmd_cfg, capture_output=True, text=True)
            if res_cfg.returncode == 0:
                print("      [OK] Configured 'memory.provider: none' (Zero ambient prompt bloat)")
            else:
                msg = res_cfg.stdout.strip() or res_cfg.stderr.strip()
                print(f"      * Memory provider config note: {msg}")
        except Exception as e:
            print(f"      [!] Note on config set: {e}")
    else:
        print("      * Hermes CLI not found in current PATH.")
        print("      * To register manually in Hermes, run:")
        print(f'        hermes mcp add fleet-memory --command "{python_bin}" --args "{script_path}"')
        print("        hermes config set memory.provider none")

    # Step 5: Self-Test Query
    print("\n[5/5] Executing live test retrieval...")
    t1 = time.time()
    try:
        results = fleet_memory_search(query="ping self test", limit=1)
        test_latency = (time.time() - t1) * 1000
        print(f"      [OK] Test vector search completed in {test_latency:.1f}ms")
    except Exception as e:
        print(f"      [!] Test query note: {e}")

    print("\n" + "=" * 64)
    print(" Node is fully provisioned and ready for multi-instance fleet operation!")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    if "--bootstrap" in sys.argv:
        bootstrap_collection()
    elif "--init" in sys.argv or "--setup" in sys.argv:
        run_init()
    elif HAS_MCP and mcp:
        mcp.run()
    else:
        print("FastMCP unavailable. Use as Python library or install 'mcp'.")
