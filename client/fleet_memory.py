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
    client = get_client()
    embedder = get_embedder()

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


if __name__ == "__main__":
    if "--bootstrap" in sys.argv:
        bootstrap_collection()
    elif HAS_MCP and mcp:
        mcp.run()
    else:
        print("FastMCP unavailable. Use as Python library or install 'mcp'.")
