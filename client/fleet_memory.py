#!/usr/bin/env python3
"""
hermes-fleet-memory
Universal FastMCP stdio server providing zero-bloat distributed vector memory,
hardware-enforced domain firewalls, and NAT-traversing execution mesh for multi-instance Hermes fleets.
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
    class DummyModels:
        class PointStruct:
            def __init__(self, id, vector, payload):
                self.id = id
                self.vector = vector
                self.payload = payload
        class FieldCondition:
            def __init__(self, **kwargs): pass
        class MatchValue:
            def __init__(self, **kwargs): pass
        class MatchAny:
            def __init__(self, **kwargs): pass
        class Filter:
            def __init__(self, **kwargs): pass
    models = DummyModels()

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

# Optional Desktop Bridge & Control Plane URLs
BRIDGE_PORT = int(os.getenv("FLEET_BRIDGE_PORT", "8099"))
FLEET_TASKS_URL = os.getenv("FLEET_TASKS_URL", "https://fleet.republikus.my").rstrip("/")
FLEET_KEY = os.getenv("FLEET_QDRANT_KEY", os.getenv("FLEET_CLUSTER_SECRET", ""))

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


def validate_domain_access(requested_domain: Optional[str] = None, is_write: bool = False) -> List[str]:
    """
    Hardware-Enforced Domain Firewall (Paradigm E++ Rule).
    
    Security Contract:
    - ENFORCED_DOMAIN == 'all': Unrestricted root (Cloud Sentinel). Can query or store in any domain.
    - ENFORCED_DOMAIN == 'work': Partition locked to Enterprise Work. Can only query/store 'work' or 'shared'.
                                Attempting to touch 'personal' raises PermissionError.
    - ENFORCED_DOMAIN == 'personal': Partition locked to Personal PC. Can only query/store 'personal' or 'shared'.
                                     Attempting to touch 'work' raises PermissionError.
    """
    if ENFORCED_DOMAIN == "all":
        if requested_domain and requested_domain != "all":
            return [requested_domain]
        return []  # Empty means search all domains without restriction

    allowed = {ENFORCED_DOMAIN, "shared"}

    if requested_domain:
        req_clean = requested_domain.lower().strip()
        if req_clean == "all":
            raise PermissionError(
                f"Domain firewall violation: Node is hardware-locked to domain '{ENFORCED_DOMAIN}' and cannot request 'all'"
            )
        if req_clean not in allowed:
            action = "write to" if is_write else "query"
            raise PermissionError(
                f"Domain firewall violation: Node is hardware-locked to domain '{ENFORCED_DOMAIN}' "
                f"and cannot {action} unauthorized domain '{req_clean}'"
            )
        return [req_clean]

    # If no target domain specified for write, defaults to node's enforced domain
    if is_write:
        return [ENFORCED_DOMAIN]

    # For read, searches both the node's enforced domain and shared cross-domain knowledge
    return list(allowed)


def fleet_memory_search(
    query: str,
    limit: int = 5,
    client_id: Optional[str] = None,
    target_domain: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search fleet memory on-demand via vector similarity.
    Query domain is hardware-enforced by host OS configuration.
    
    Parameters:
    - query: Natural language search string.
    - limit: Maximum number of points to retrieve.
    - client_id: Optional filter for a specific client/subsystem.
    - target_domain: "personal", "work", "shared", or "all". Validated against FLEET_HARD_DOMAIN.
    """
    domains_to_search = validate_domain_access(target_domain, is_write=False)

    try:
        client = get_client()
        embedder = get_embedder()
        raw_vec = list(embedder.embed([query]))[0]
        vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)

        must_conditions = [
            models.FieldCondition(key="status", match=models.MatchValue(value="active"))
        ]

        # Apply strict domain firewall filters
        if domains_to_search:
            if len(domains_to_search) == 1:
                must_conditions.append(
                    models.FieldCondition(key="domain", match=models.MatchValue(value=domains_to_search[0]))
                )
            else:
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
                "revision": payload.get("revision", 1),
                "created_at": payload.get("created_at", 0),
                "updated_at": payload.get("updated_at", payload.get("created_at", 0))
            })
        return output
    except PermissionError:
        raise
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
    pinned: bool = False,
    timestamp: Optional[float] = None
) -> Dict[str, Any]:
    """
    Store or update an authoritative card in fleet memory.
    Enforces Last-Write-Wins (LWW) conflict resolution and deterministic UUID5 slot overwrites.
    
    Parameters:
    - text: Markdown content or factual statement to store.
    - client_id: Component or subsystem identifier (e.g., "hardware", "payment_gateway").
    - slot_name: Unique slot name. If provided, updates existing record in-place via deterministic UUID5.
    - target_domain: "personal", "work", or "shared". Validated against FLEET_HARD_DOMAIN.
    - pinned: If True, protects from the 90-day episodic expiry cleaner.
    - timestamp: Optional explicit epoch timestamp for LWW replication.
    """
    # Hardware domain firewall validation
    valid_domains = validate_domain_access(target_domain, is_write=True)
    effective_domain = valid_domains[0] if valid_domains else (target_domain or "shared")
    if effective_domain == "all":
        effective_domain = "shared"

    now = timestamp if timestamp is not None else time.time()
    revision = 1

    # Deterministic slot overwrite using UUID5 with Last-Write-Wins (LWW) check
    if slot_name and client_id:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{effective_domain}:{client_id}:{slot_name}"))
        is_pinned = True
        
        # Concurrency check: retrieve existing point payload if present
        try:
            client = get_client()
            existing_points = client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[point_id],
                with_payload=True
            )
            if existing_points:
                existing = existing_points[0]
                existing_payload = existing.payload or {}
                existing_updated = float(existing_payload.get("updated_at", existing_payload.get("created_at", 0)))
                existing_rev = int(existing_payload.get("revision", 1))

                # LWW Conflict Resolution: Drop stale write if older than existing point
                if timestamp is not None and timestamp < existing_updated:
                    return {
                        "status": "conflict_rejected",
                        "id": point_id,
                        "domain": effective_domain,
                        "message": f"Stale write rejected by Last-Write-Wins (LWW). Existing point updated at {existing_updated}, write was {timestamp}.",
                        "current_revision": existing_rev
                    }
                revision = existing_rev + 1
        except Exception:
            # Fall open for test environments or new collections
            pass
    else:
        point_id = str(uuid.uuid4())
        is_pinned = pinned

    try:
        client = get_client()
        embedder = get_embedder()
        raw_vec = list(embedder.embed([text]))[0]
        vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)

        payload = {
            "text": text,
            "domain": effective_domain,
            "client_id": client_id or "generic",
            "slot_name": slot_name or "episodic",
            "status": "active",
            "pinned": is_pinned,
            "revision": revision,
            "created_at": int(now),
            "updated_at": float(now),
            "expires_at": 0 if is_pinned else int(now + (90 * 86400))
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
            "pinned": is_pinned,
            "revision": revision
        }
    except PermissionError:
        raise
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
        description="Read an authorized file under user home directory on the target workstation."
    )
    def desktop_read_file(path: str) -> Dict[str, Any]:
        """Read an authorized document from the workstation."""
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
        description="Manage remote workstation power: shutdown, restart, or cancel pending power actions."
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

    @mcp.tool(
        name="fleet_task_delegate",
        description="Asynchronously delegate a task to another fleet node (e.g. 'chester' for Telegram alerts/health checks, 'winston' for GPU batches)."
    )
    def fleet_task_delegate(
        target_node: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Asynchronously delegate an allowlisted task to another fleet node.
        - target_node: Target node ('chester', 'winston').
        - action: Action to perform ('telegram_notify', 'fleet_health_ping', 'gpu_batch').
        - params: Parameters dict (e.g. {'message': 'Hello from Levi'}).
        - priority: 'low', 'normal', or 'critical'.
        """
        import json, urllib.request, urllib.error
        if not FLEET_KEY:
            return {
                "status": "error",
                "message": "Missing FLEET_KEY. Configure FLEET_KEY in environment or ~/.hermes/fleet_auth.json."
            }
        
        idempotency_key = f"mcp_{action}_{int(time.time() * 1000)}"
        payload = {
            "target": target_node.lower(),
            "action": action,
            "priority": priority.lower(),
            "params": params or {},
            "idempotency_key": idempotency_key
        }
        
        url = f"{FLEET_TASKS_URL}/api/fleet/tasks"
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {FLEET_KEY}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return {
                    "status": "accepted",
                    "task_id": res.get("task_id"),
                    "task_status": res.get("status"),
                    "target": target_node,
                    "action": action,
                    "eta_seconds": res.get("eta_seconds", 1),
                    "message": f"Task successfully queued for {target_node}. Use fleet_task_status(task_id='{res.get('task_id')}') to verify receipt."
                }
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"status": "error", "message": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to reach Fleet Task Plane at {url}: {e}"}

    @mcp.tool(
        name="fleet_task_status",
        description="Check execution status and verify Ed25519 cryptographic completion receipt for a delegated fleet task."
    )
    def fleet_task_status(task_id: str, verify_receipt: bool = True) -> Dict[str, Any]:
        """
        Check the status and verify Ed25519 completion receipt for a delegated task.
        """
        import json, urllib.request, urllib.error
        if not FLEET_KEY:
            return {
                "status": "error",
                "message": "Missing FLEET_KEY. Configure FLEET_KEY in environment or ~/.hermes/fleet_auth.json."
            }
            
        url = f"{FLEET_TASKS_URL}/api/fleet/tasks/{task_id}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {FLEET_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                task_data = json.loads(resp.read().decode("utf-8"))
                
            verified = None
            if verify_receipt and task_data.get("status") == "completed" and task_data.get("ed25519_signature"):
                try:
                    from cryptography.hazmat.primitives.asymmetric import ed25519
                    keys_url = f"{FLEET_TASKS_URL}/.well-known/fleet-keys.json"
                    with urllib.request.urlopen(keys_url, timeout=5) as k_resp:
                        jwks = json.loads(k_resp.read().decode("utf-8"))
                        pub_hex = jwks["keys"][0]["x"]
                    pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
                    receipt_payload = {
                        "completed_at": round(task_data["completed_at"], 3),
                        "result": task_data["result"],
                        "task_id": task_data["task_id"]
                    }
                    canonical = json.dumps(receipt_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
                    pub_key.verify(bytes.fromhex(task_data["ed25519_signature"]), canonical)
                    verified = True
                except Exception as e:
                    verified = False
                    task_data["verification_error"] = str(e)
                    
            return {
                "status": task_data.get("status"),
                "task_id": task_data.get("task_id"),
                "target": task_data.get("target"),
                "action": task_data.get("action"),
                "result": task_data.get("result"),
                "error": task_data.get("error"),
                "receipt_verified": verified,
                "kid": task_data.get("kid"),
                "created_at": task_data.get("created_at"),
                "completed_at": task_data.get("completed_at")
            }
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"status": "error", "message": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to query task status at {url}: {e}"}


def bootstrap_collection():
    """
    Bootstrap the Qdrant vector collection with INT8 Scalar Quantization (SQ)
    and optimized HNSW parameters for 4x memory savings on resource-constrained nodes.
    """
    client = get_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True
                )
            ),
            hnsw_config=models.HnswConfigDiff(
                m=16,
                ef_construct=100
            )
        )
        for field in ["domain", "client_id", "status", "memory_type", "pinned", "revision"]:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD
            )
        print(f"Collection '{COLLECTION_NAME}' bootstrapped successfully with INT8 Scalar Quantization.")
    else:
        print(f"Collection '{COLLECTION_NAME}' already active.")


if __name__ == "__main__":
    if "--bootstrap" in sys.argv:
        bootstrap_collection()
    elif HAS_MCP and mcp:
        mcp.run()
    else:
        print("FastMCP unavailable. Use as Python library or install 'mcp'.")
