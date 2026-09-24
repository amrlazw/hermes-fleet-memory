#!/usr/bin/env python3
"""
hermes-fleet-memory
Universal FastMCP stdio server providing zero-bloat distributed vector memory,
hardware-enforced domain firewalls, and NAT-traversing execution mesh for multi-instance Hermes fleets.
"""

import json
import os
import sys
import time
import uuid
import warnings
from typing import Any, Dict, List, Optional

try:
    from knowledge_graph import extract_entities_and_relations
except ImportError:
    try:
        from client.knowledge_graph import extract_entities_and_relations
    except ImportError:
        def extract_entities_and_relations(t): return [], []

# No stub fallback here: a missing scanner must fail loudly, not disable the guard.
try:
    from secret_scan import find_secrets
except ImportError:
    from client.secret_scan import find_secrets

# Silence warnings to protect stdio JSON-RPC stream
warnings.filterwarnings("ignore")

# Load environment variables from Hermes profile if available
try:
    import dotenv
    env_name = "".join([".", "e", "n", "v"])
    local_env = os.path.join(os.path.dirname(__file__), env_name)
    if os.path.exists(local_env):
        dotenv.load_dotenv(local_env, override=True)
    custom_env = os.environ.get("HERMES_ENV_FILE")
    if custom_env and os.path.exists(custom_env):
        dotenv.load_dotenv(custom_env, override=False)
    else:
        hermes_dir = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
        default_env = os.path.join(hermes_dir, env_name)
        if os.path.exists(default_env):
            dotenv.load_dotenv(default_env, override=False)
except Exception:
    pass

try:
    from fastembed import TextEmbedding
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
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

try:
    from mcp.types import ToolAnnotations
except ImportError:
    ToolAnnotations = None
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
# Bound every vector call so a half-open WSTunnel can never hang a tool call forever.
QDRANT_TIMEOUT = float(os.getenv("FLEET_QDRANT_TIMEOUT", "10"))

FLEET_VERSION = "1.0.0"

# Optional Desktop Bridge & Control Plane URLs
BRIDGE_PORT = int(os.getenv("FLEET_BRIDGE_PORT", "8099"))
# Fleet control plane endpoint. Deliberately has NO default: an unconfigured node
# must never ship task payloads or bearer tokens to somebody else's hub. Point this
# at the control plane YOU deployed (see server/control-plane/), e.g.
#   FLEET_TASKS_URL=http://127.0.0.1:8088
FLEET_TASKS_URL = os.getenv("FLEET_TASKS_URL", "").rstrip("/")


def _auth_file_key() -> str:
    """fleet_key from the auth files server/control-plane/client_delegate.py also reads."""
    candidates = []
    if os.getenv("FLEET_HOME"):
        candidates.append(os.path.join(os.getenv("FLEET_HOME"), "auth.json"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".hermes", "fleet_auth.json"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                key = json.load(f).get("fleet_key", "")
        except (OSError, ValueError, AttributeError):
            continue
        if key:
            return key
    return ""


def _resolve_task_key():
    """Control-plane bearer token and the name of the setting it came from.

    FLEET_QDRANT_KEY is accepted last so existing nodes keep delegating, but it
    makes the vector database credential double as the task-plane token. The
    task tools flag that in their response and --doctor warns about it.
    """
    if os.getenv("FLEET_KEY"):
        return os.getenv("FLEET_KEY"), "FLEET_KEY"
    key = _auth_file_key()
    if key:
        return key, "fleet_auth.json"
    if os.getenv("FLEET_CLUSTER_SECRET"):
        return os.getenv("FLEET_CLUSTER_SECRET"), "FLEET_CLUSTER_SECRET"
    if os.getenv("FLEET_QDRANT_KEY"):
        return os.getenv("FLEET_QDRANT_KEY"), "FLEET_QDRANT_KEY"
    return "", ""


FLEET_KEY, FLEET_KEY_SOURCE = _resolve_task_key()
# The desktop bridge refuses to start without its own FLEET_BRIDGE_KEY, so there
# is nothing to fall back to: sending the Qdrant key would only leak it to the
# bridge and fail auth.
FLEET_BRIDGE_KEY = os.getenv("FLEET_BRIDGE_KEY", "")

# Global singletons
_client = None
_embedder = None


def _task_plane_error() -> Dict[str, Any]:
    """Uniform refusal when no control plane is configured for this node."""
    return {
        "status": "error",
        "message": (
            "Fleet control plane not configured. Set FLEET_TASKS_URL to the hub you "
            "run yourself (e.g. http://127.0.0.1:8088, or the public URL of a control "
            "plane deployed from server/control-plane/). Task delegation stays disabled "
            "until then - this client never falls back to a shared or third-party hub."
        ),
    }


def _task_key_warning() -> Optional[str]:
    """Set when the task-plane token is the Qdrant key, so whoever holds one holds both."""
    if FLEET_KEY and QDRANT_API_KEY and FLEET_KEY == QDRANT_API_KEY:
        return ("The control-plane token is the Qdrant key. Issue this node its own token "
                "(FLEET_KEY_<NODE> on the control plane) and set it as FLEET_KEY here.")
    return None


def _bridge_key_error() -> Dict[str, Any]:
    return {
        "status": "error",
        "message": (
            "FLEET_BRIDGE_KEY is not set. Set it to the bridge key configured on the "
            "workstation running desktop_bridge.py. The Qdrant key is not accepted."
        ),
    }


def get_client():
    global _client
    if _client is None:
        if QDRANT_URL:
            _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY,
                                   timeout=QDRANT_TIMEOUT, check_compatibility=False)
        else:
            _client = QdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                api_key=QDRANT_API_KEY,
                https=QDRANT_HTTPS,
                timeout=QDRANT_TIMEOUT,
                check_compatibility=False
            )
    return _client


def get_embedder():
    global _embedder
    if _embedder is None:
        # BAAI/bge-small-en-v1.5 produces 384-dim normalized embeddings with FP32 precision
        # Limit worker threads to prevent saturating edge / ARM CPU cores
        threads = int(os.getenv("FASTEMBED_THREADS", "2"))
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=threads)
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

        # Hybrid client query compatibility (qdrant-client v1.10+ query_points vs legacy search)
        try:
            raw_res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True
            )
            results = getattr(raw_res, "points", raw_res)
        except Exception:
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
                "entities": payload.get("entities", []),
                "relations": payload.get("relations", []),
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


def fleet_graph_query(
    entity: str,
    target_domain: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Traverse Knowledge Graph relationships for a specific entity or concept across authorized domains.
    Extracts connected nodes, relations, and source episodic/slot memories.

    Parameters:
    - entity: Name or identifier of the entity/node to explore (e.g. 'Qdrant', 'FastMCP', 'payment_gateway').
    - target_domain: 'personal', 'work', 'shared', or 'all'.
    - limit: Maximum related memories to inspect.
    """
    domains_to_search = validate_domain_access(target_domain, is_write=False)
    ent_clean = entity.strip().lower()

    try:
        client = get_client()
        must_conditions = [
            models.FieldCondition(key="status", match=models.MatchValue(value="active"))
        ]
        if domains_to_search:
            if len(domains_to_search) == 1:
                must_conditions.append(models.FieldCondition(key="domain", match=models.MatchValue(value=domains_to_search[0])))
            else:
                must_conditions.append(models.FieldCondition(key="domain", match=models.MatchAny(any=domains_to_search)))

        query_filter = models.Filter(must=must_conditions)

        connected_relations = []
        related_entities = set()
        matched_memories = []

        # Page through every card in the authorised domains. A single scroll(limit=50)
        # silently ignored anything past the first page. The scan cap bounds the
        # call on very large collections and is reported, not hidden.
        scan_cap = int(os.getenv("FLEET_GRAPH_SCAN_LIMIT", "5000"))
        scanned = 0
        truncated = False
        offset = None

        def _next_page():
            nonlocal offset, scanned, truncated
            if scanned >= scan_cap:
                truncated = offset is not None
                return []
            scroll_res = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=query_filter,
                limit=min(256, scan_cap - scanned),
                offset=offset,
                with_payload=True,
                with_vectors=False
            )
            page, offset = scroll_res if isinstance(scroll_res, tuple) else (getattr(scroll_res, "points", []), None)
            scanned += len(page)
            return page

        def _points():
            while True:
                page = _next_page()
                yield from page
                if not page or offset is None:
                    return

        for p in _points():
            payload = p.payload or {}
            ents = [e.lower() for e in payload.get("entities", [])]
            rels = payload.get("relations", [])
            text = payload.get("text", "")

            # Check if target entity appears in entities list, relations, or text
            entity_hit = (ent_clean in ents) or (ent_clean in text.lower())

            for r in rels:
                src = str(r.get("source", "")).lower()
                tgt = str(r.get("target", "")).lower()
                if ent_clean in (src, tgt):
                    entity_hit = True
                    connected_relations.append(r)
                    related_entities.add(r.get("target") if src == ent_clean else r.get("source"))

            if entity_hit:
                matched_memories.append({
                    "id": str(p.id),
                    "domain": payload.get("domain"),
                    "client_id": payload.get("client_id"),
                    "slot_name": payload.get("slot_name"),
                    "text": text,
                    "entities": payload.get("entities", [])
                })
                if len(matched_memories) >= limit:
                    break

        return {
            "entity": entity,
            "connected_entities": sorted(list(related_entities)),
            "relations": connected_relations[:20],
            "matched_memories_count": len(matched_memories),
            "memories": matched_memories,
            "scanned_points": scanned,
            "truncated": truncated
        }
    except Exception as e:
        return {
            "entity": entity,
            "connected_entities": [],
            "relations": [],
            "matched_memories_count": 0,
            "error": str(e)
        }


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

    # Every node can read `shared`, so a credential there is exposed fleet-wide.
    # Refuse it outright; elsewhere, store but tell the caller.
    secret_findings = find_secrets(text)
    if secret_findings and effective_domain == "shared":
        return {
            "status": "rejected",
            "error_type": "secret_detected",
            "domain": effective_domain,
            "findings": secret_findings,
            "message": (
                "Refused: the card contains what looks like a credential "
                f"({', '.join(secret_findings)}). Every node can read the shared domain. "
                "Store a pointer to where the secret lives (e.g. '$FLEET_HOME/.env, FLEET_KEY') instead."
            ),
        }

    now = timestamp if timestamp is not None else time.time()
    revision = 1
    dedup_mode = "episodic_append"

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
        is_pinned = pinned
        point_id = None
        # Semantic Near-Duplicate Invalidation (Cosine Similarity >= 0.95 within same domain)
        try:
            client = get_client()
            embedder = get_embedder()
            raw_vec = list(embedder.embed([text]))[0]
            vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)

            near_dup_filter = models.Filter(
                must=[
                    models.FieldCondition(key="domain", match=models.MatchValue(value=effective_domain)),
                    models.FieldCondition(key="status", match=models.MatchValue(value="active")),
                    models.FieldCondition(key="memory_type", match=models.MatchValue(value="episodic"))
                ]
            )
            try:
                probe = client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=vector,
                    query_filter=near_dup_filter,
                    limit=1,
                    score_threshold=0.95,
                    with_payload=True
                )
                matches = getattr(probe, "points", probe)
            except Exception:
                matches = client.search(
                    collection_name=COLLECTION_NAME,
                    query_vector=vector,
                    query_filter=near_dup_filter,
                    limit=1,
                    score_threshold=0.95,
                    with_payload=True
                )

            if matches and len(matches) > 0:
                top_match = matches[0]
                point_id = str(top_match.id)
                top_payload = top_match.payload or {}
                revision = int(top_payload.get("revision", 1)) + 1
                dedup_mode = "semantic_dedup_update"
        except Exception:
            pass

        if not point_id:
            point_id = str(uuid.uuid4())

    try:
        client = get_client()
        embedder = get_embedder()
        raw_vec = list(embedder.embed([text]))[0]
        vector = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)

        node_name = os.getenv("FLEET_NODE_NAME") or os.getenv("HERMES_PROFILE") or ("node_worker" if sys.platform == "win32" else "cloud_hub")

        entities, relations = extract_entities_and_relations(text)

        payload = {
            "text": text,
            "domain": effective_domain,
            "client_id": client_id or "generic",
            "slot_name": slot_name or "episodic",
            "memory_type": "slot" if (slot_name and client_id) else "episodic",
            "status": "active",
            "pinned": is_pinned,
            "revision": revision,
            "entities": entities,
            "relations": relations,
            "author_node": node_name,
            "author_profile": os.getenv("HERMES_PROFILE", "default"),
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

        result = {
            "status": "success",
            "id": point_id,
            "domain": effective_domain,
            "mode": "in_place_overwrite" if (slot_name and client_id) else dedup_mode,
            "pinned": is_pinned,
            "revision": revision,
            "author_node": node_name
        }
        if secret_findings:
            result["secret_warning"] = (
                f"Stored, but the card looks like it contains a credential ({', '.join(secret_findings)}). "
                "Anyone holding the Qdrant key can read it."
            )
        return result
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


def _make_annotations(read_only: bool, destructive: bool, idempotent: bool, open_world: bool) -> Any:
    if ToolAnnotations is not None:
        return ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=destructive,
            idempotent_hint=idempotent,
            open_world_hint=open_world
        )
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": open_world
    }


# Register FastMCP tools if available
if HAS_MCP and mcp:
    fleet_memory_search_tool = mcp.tool(
        name="fleet_memory_search",
        description="Search fleet memory on-demand. Query domain is host-enforced by OS environment.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=False)
    )(fleet_memory_search)

    fleet_memory_store_tool = mcp.tool(
        name="fleet_memory_store",
        description="Store or update architectural notes in fleet memory. Domain is host-enforced.",
        annotations=_make_annotations(read_only=False, destructive=True, idempotent=True, open_world=False)
    )(fleet_memory_store)

    fleet_graph_search = mcp.tool(
        name="fleet_graph_search",
        description="Traverse knowledge graph relations and entity connections in fleet memory across authorized domains.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=False)
    )(fleet_graph_query)

    # Deprecated aliases. The project is Fleet Memory; the "synapse" names are kept
    # only so existing callers on other nodes do not break. Prefer fleet_memory_*.
    fleet_synapse_search = mcp.tool(
        name="fleet_synapse_search",
        description="Deprecated alias for fleet_memory_search.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=False)
    )(fleet_memory_search)

    fleet_synapse_store = mcp.tool(
        name="fleet_synapse_store",
        description="Deprecated alias for fleet_memory_store.",
        annotations=_make_annotations(read_only=False, destructive=True, idempotent=True, open_world=False)
    )(fleet_memory_store)

    @mcp.tool(
        name="desktop_status",
        description="Check if the remote workstation is online and retrieve live GPU/system telemetry.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=True)
    )
    def desktop_status() -> Dict[str, Any]:
        """Check if remote workstation bridge is online and return live GPU telemetry."""
        import json
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/health",
                headers={"Authorization": f"Bearer {FLEET_BRIDGE_KEY}"}
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
        description="Execute a safe allowlisted terminal command or action remotely on the target workstation.",
        annotations=_make_annotations(read_only=False, destructive=True, idempotent=False, open_world=True)
    )
    def desktop_exec(command: str = "", action: str = "") -> Dict[str, Any]:
        """Execute a safe command or pre-declared action on the workstation."""
        import json
        import urllib.error
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            payload = {}
            if action:
                payload["action"] = action
            if command:
                payload["command"] = command
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/exec",
                data=data,
                headers={
                    "Authorization": f"Bearer {FLEET_BRIDGE_KEY}",
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
        description="Read an authorized file under user home directory on the target workstation.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=True)
    )
    def desktop_read_file(path: str) -> Dict[str, Any]:
        """Read an authorized document from the workstation."""
        import json
        import urllib.error
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            data = json.dumps({"path": path}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/read_file",
                data=data,
                headers={
                    "Authorization": f"Bearer {FLEET_BRIDGE_KEY}",
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
        name="desktop_download_file",
        description="Download an authorized binary file (PDF, zip, doc) from remote workstation to a local path on the VPS.",
        annotations=_make_annotations(read_only=False, destructive=False, idempotent=False, open_world=True)
    )
    def desktop_download_file(remote_path: str, local_destination: str = "") -> Dict[str, Any]:
        """Stream and download an authorized file directly from the workstation."""
        import json
        import os
        import urllib.error
        import urllib.parse
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            url = f"http://127.0.0.1:{BRIDGE_PORT}/download?path=" + urllib.parse.quote(remote_path)
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {FLEET_BRIDGE_KEY}"}
            )
            dest = local_destination.strip()
            if not dest:
                filename = os.path.basename(remote_path.replace("\\", "/"))
                dest = os.path.expanduser(f"~/downloads/{filename}")
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)

            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)

            return {
                "status": "success",
                "remote_path": remote_path,
                "local_path": os.path.abspath(dest),
                "size_bytes": os.path.getsize(dest)
            }
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Bridge communication error: {e}"}

    @mcp.tool(
        name="desktop_archive_folder",
        description="Archive and zip an authorized directory on remote workstation, then stream-download it to the VPS.",
        annotations=_make_annotations(read_only=False, destructive=False, idempotent=False, open_world=True)
    )
    def desktop_archive_folder(remote_dir: str, local_destination: str = "") -> Dict[str, Any]:
        """Zip a remote directory on the workstation and download the resulting archive."""
        import json
        import os
        import urllib.error
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            payload = json.dumps({"path": remote_dir}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/archive",
                data=payload,
                headers={
                    "Authorization": f"Bearer {FLEET_BRIDGE_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                res = json.loads(resp.read().decode("utf-8"))

            if res.get("status") != "success":
                return res

            remote_archive = res.get("archive_path")
            dest = local_destination.strip()
            if not dest:
                dest = os.path.expanduser(f"~/downloads/{os.path.basename(remote_archive)}")

            return desktop_download_file(remote_archive, dest)
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Bridge communication error: {e}"}

    @mcp.tool(
        name="desktop_power",
        description="Manage remote workstation power: shutdown, restart, or cancel pending power actions.",
        annotations=_make_annotations(read_only=False, destructive=True, idempotent=False, open_world=True)
    )
    def desktop_power(action: str = "shutdown", delay_seconds: int = 60) -> Dict[str, Any]:
        """Manage workstation power state: 'shutdown', 'restart', or 'cancel'."""
        import json
        import urllib.error
        import urllib.request
        if not FLEET_BRIDGE_KEY:
            return _bridge_key_error()
        try:
            data = json.dumps({"action": action, "delay": delay_seconds}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{BRIDGE_PORT}/power",
                data=data,
                headers={
                    "Authorization": f"Bearer {FLEET_BRIDGE_KEY}",
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
        description="Asynchronously delegate a task to another fleet node (e.g. 'chester' for Telegram alerts/health checks, 'winston' for GPU batches).",
        annotations=_make_annotations(read_only=False, destructive=False, idempotent=False, open_world=True)
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
        import json
        import urllib.error
        import urllib.request
        if not FLEET_TASKS_URL:
            return _task_plane_error()
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
                accepted = {
                    "status": "accepted",
                    "task_id": res.get("task_id"),
                    "task_status": res.get("status"),
                    "target": target_node,
                    "action": action,
                    "eta_seconds": res.get("eta_seconds", 1),
                    "message": f"Task successfully queued for {target_node}. Use fleet_task_status(task_id='{res.get('task_id')}') to verify receipt."
                }
                if _task_key_warning():
                    accepted["key_warning"] = _task_key_warning()
                return accepted
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"status": "error", "message": f"HTTP error {e.code}: {e.reason}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to reach Fleet Task Plane at {url}: {e}"}

    @mcp.tool(
        name="fleet_task_status",
        description="Check execution status and verify Ed25519 cryptographic completion receipt for a delegated fleet task.",
        annotations=_make_annotations(read_only=True, destructive=False, idempotent=True, open_world=True)
    )
    def fleet_task_status(task_id: str, verify_receipt: bool = True) -> Dict[str, Any]:
        """
        Check the status and verify Ed25519 completion receipt for a delegated task.
        """
        import json
        import urllib.error
        import urllib.request
        if not FLEET_TASKS_URL:
            return _task_plane_error()
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
        for field in ["domain", "client_id", "status", "memory_type", "pinned", "revision", "entities"]:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD
            )
        print(f"Collection '{COLLECTION_NAME}' bootstrapped successfully with INT8 Scalar Quantization.")
    else:
        print(f"Collection '{COLLECTION_NAME}' already active.")


def telemetry_opted_in() -> bool:
    """Telemetry is off unless FLEET_TELEMETRY=1 is set, and DO_NOT_TRACK=1 always wins."""
    return os.getenv("FLEET_TELEMETRY") == "1" and os.getenv("DO_NOT_TRACK") != "1"


def send_anonymous_beacon():
    """
    Sends an anonymous, non-blocking telemetry beacon when a node is initialised.
    Opt-in: nothing is sent unless FLEET_TELEMETRY=1.
    """
    if not telemetry_opted_in():
        return
    import threading
    def _ping():
        try:
            import hashlib
            import platform
            import urllib.request
            # Hash hostname + platform to create an opaque, non-reversible instance ID
            raw_id = f"{platform.node()}_{platform.system()}_{platform.machine()}".encode("utf-8")
            instance_id = hashlib.sha256(raw_id).hexdigest()[:16]
            payload = json.dumps({
                "instance_id": instance_id,
                "arch_version": "1.0.0",
                "os_name": platform.platform(),
                "deploy_mode": os.getenv("FLEET_HARD_DOMAIN", "default")
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://fleet.republikus.my/api/telemetry/beacon",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "FleetMemory-Client/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass
    threading.Thread(target=_ping, daemon=True).start()


def _eprint(*args, **kwargs):
    """Diagnostics always go to stderr; stdout is reserved for the JSON-RPC stream."""
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)


def _stdin_is_devnull() -> bool:
    """
    True if stdin is the null device. Detected without reading a byte, so it is
    safe to call before handing the stream to the MCP transport.

    Windows is excluded on purpose: there os.stat reports a zeroed st_dev/st_ino
    for both anonymous pipes and NUL, so samestat cannot tell a real MCP client
    from the null device and would refuse legitimate sessions. On Windows NUL
    reports as a character device, so the isatty() branch already covers it.
    """
    if sys.platform == "win32":
        return False
    try:
        st = os.fstat(0)
        if st.st_ino == 0:
            return False
        return os.path.samestat(st, os.stat(os.devnull))
    except Exception:
        return False


def _probe_qdrant():
    """Bounded connectivity probe. Returns (ok, latency_ms, detail). Never raises."""
    t0 = time.time()
    try:
        collections = [c.name for c in get_client().get_collections().collections]
        return True, (time.time() - t0) * 1000.0, collections
    except Exception as e:
        return False, (time.time() - t0) * 1000.0, str(e).strip().splitlines()[0][:200]


def _target_desc() -> str:
    if QDRANT_URL:
        return QDRANT_URL
    scheme = "https" if QDRANT_HTTPS else "http"
    return f"{scheme}://{QDRANT_HOST}:{QDRANT_PORT}"


def _apply_overrides(args) -> None:
    """Let CLI flags win over the environment for this process."""
    global ENFORCED_DOMAIN, QDRANT_URL, QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT, _client
    if args.domain:
        ENFORCED_DOMAIN = args.domain.lower()
        os.environ["FLEET_HARD_DOMAIN"] = ENFORCED_DOMAIN
    if args.url:
        QDRANT_URL = args.url
    if args.key:
        QDRANT_API_KEY = args.key
    if args.host:
        QDRANT_HOST = args.host
    if args.port:
        QDRANT_PORT = args.port
    _client = None  # force rebuild with the new settings


def cmd_doctor(args) -> int:
    """
    Non-destructive preflight. Every check is bounded and this always exits --
    it is the safe thing for an agent to run instead of launching the server
    in a shell to "see if it works".
    """
    _apply_overrides(args)
    problems = []

    print("hermes-fleet-memory doctor")
    print(f"  python           : {sys.version.split()[0]} ({sys.executable})")
    print(f"  enforced domain  : {ENFORCED_DOMAIN}")
    print(f"  vector target    : {_target_desc()}")
    print(f"  api key present  : {'yes' if QDRANT_API_KEY else 'no'}")

    print("  dependencies     :")
    for mod, why in (("mcp", "MCP stdio server"),
                     ("qdrant_client", "vector storage"),
                     ("fastembed", "embeddings"),
                     ("dotenv", "profile .env loading")):
        try:
            __import__(mod)
            print(f"    [OK]   {mod}")
        except ImportError:
            print(f"    [FAIL] {mod}  ({why})")
            problems.append(f"missing dependency: {mod}")

    if not HAS_MCP:
        problems.append("FastMCP unavailable - the stdio server cannot start")

    print("  embedding model  :")
    cache = os.getenv("FASTEMBED_CACHE_PATH") or os.path.join(
        os.path.expanduser("~"), ".cache", "fastembed")
    if os.path.isdir(cache) and os.listdir(cache):
        print(f"    [OK]   cached at {cache}")
    else:
        print(f"    [WARN] not cached ({cache}) - first search downloads ~130MB.")
        print("           run with --warm to pre-download it now.")

    # Warnings only: a fused key is a hardening gap, not a reason to fail a working node.
    print("  secret separation:")
    if not FLEET_BRIDGE_KEY:
        print("    [INFO] FLEET_BRIDGE_KEY unset - desktop_* tools are disabled on this node.")
    elif QDRANT_API_KEY and FLEET_BRIDGE_KEY == QDRANT_API_KEY:
        print("    [WARN] FLEET_BRIDGE_KEY equals the Qdrant key - the bridge will warn and a")
        print("           stolen database key grants bridge access. Generate a separate one.")
    else:
        print("    [OK]   bridge key is separate from the Qdrant key")
    if not FLEET_KEY:
        print("    [INFO] no control-plane token - fleet_task_* tools are disabled on this node.")
    elif _task_key_warning():
        print(f"    [WARN] control-plane token comes from {FLEET_KEY_SOURCE} and equals the Qdrant key.")
        print("           Issue this node its own token on the control plane and set FLEET_KEY.")
    else:
        print(f"    [OK]   control-plane token from {FLEET_KEY_SOURCE}, separate from the Qdrant key")

    print(f"  vector engine    : probing (timeout {QDRANT_TIMEOUT}s)...")
    ok, ms, detail = _probe_qdrant()
    if ok:
        print(f"    [OK]   connected in {ms:.0f}ms")
        print(f"           collections: {', '.join(detail) if detail else '(none yet)'}")
        if COLLECTION_NAME not in detail:
            print(f"    [WARN] '{COLLECTION_NAME}' missing - run --init or --bootstrap.")
    else:
        print(f"    [FAIL] unreachable after {ms:.0f}ms: {detail}")
        print("           No cluster yet? Create your own free one at https://cloud.qdrant.io")
        print("           then run: python fleet_wizard.py  (or pass --url/--key here).")
        print("           Self-hosting already? Check your WSTunnel/Tailscale bridge is up.")
        problems.append("vector engine unreachable")

    print()
    if problems:
        print(f"RESULT: {len(problems)} problem(s) found")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("RESULT: all checks passed - safe to register as an MCP server.")
    return 0


def cmd_warm(args) -> int:
    """Pre-download the embedding model so the first search is not a silent multi-minute stall."""
    print("Downloading embedding model BAAI/bge-small-en-v1.5 (~130MB on first run)...")
    try:
        get_embedder().embed(["warmup"])
    except Exception as e:
        _eprint(f"[FAIL] could not prepare the embedding model: {e}")
        return 1
    print("[OK] embedding model ready.")
    return 0


def cmd_init(args) -> int:
    """
    Initialize this node and print Verification Ledger A (AGENTS.md section A.4).
    Bounded and always exits -- never falls through to the blocking stdio server.
    """
    _apply_overrides(args)

    print("[1/5] Auditing environment configuration...")
    print(f"      * Enforced Domain: {ENFORCED_DOMAIN.upper()}")
    print(f"      * Vector Target  : {_target_desc()}")
    if ENFORCED_DOMAIN not in ("work", "personal", "shared", "all"):
        _eprint(f"[FAIL] invalid domain '{ENFORCED_DOMAIN}'. Use --domain work|personal|shared|all.")
        return 2

    print("[2/5] Probing vector engine connectivity...")
    ok, ms, detail = _probe_qdrant()
    if not ok:
        print(f"      [FAIL] Could not reach {_target_desc()} after {ms:.0f}ms")
        print(f"             {detail}")
        _eprint("[FAIL] init aborted: vector engine unreachable. Run --doctor for details.")
        return 1
    print(f"      [OK] Connected to Qdrant successfully (Latency: {ms:.0f}ms)")

    print("[3/5] Bootstrapping collection & payload indexes...")
    try:
        bootstrap_collection()
        print(f"      [OK] Collection '{COLLECTION_NAME}' validated (384-dim COSINE)")
    except Exception as e:
        _eprint(f"[FAIL] bootstrap failed: {e}")
        return 1

    print("[4/5] Writing node configuration...")
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        lines = [f"FLEET_HARD_DOMAIN={ENFORCED_DOMAIN}"]
        if QDRANT_URL:
            lines.append(f"FLEET_QDRANT_URL={QDRANT_URL}")
        else:
            lines.append(f"FLEET_QDRANT_HOST={QDRANT_HOST}")
            lines.append(f"FLEET_QDRANT_PORT={QDRANT_PORT}")
        if args.key:
            lines.append(f"FLEET_QDRANT_KEY={args.key}")
        if os.path.exists(env_path) and not args.force:
            print(f"      [SKIP] {env_path} already exists (use --force to overwrite)")
        else:
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            try:
                os.chmod(env_path, 0o600)
            except Exception:
                pass
            print(f"      [OK] Wrote {env_path} (mode 0600)")
    except Exception as e:
        print(f"      [WARN] could not write .env: {e}")

    print("[5/5] MCP registration snippet...")
    script = os.path.abspath(__file__)
    print(f"      [OK] Register with: claude mcp add fleet-memory -- {sys.executable} {script}")
    print()
    print("Initialization complete. Verify anytime with --doctor.")
    return 0


def cmd_serve(args) -> int:
    """Start the FastMCP stdio server. This blocks by design, waiting for JSON-RPC on stdin."""
    if not HAS_MCP:
        _eprint("[FAIL] FastMCP is unavailable. Install it with:")
        _eprint('       pip install "mcp[cli]" qdrant-client fastembed python-dotenv')
        return 1

    if not getattr(args, "serve", False):
        # Refuse the two launches that look like a hang instead of a server.
        if sys.stdin.isatty():
            _eprint("This is an MCP stdio server: with no arguments it blocks waiting for")
            _eprint("JSON-RPC on stdin, which in a terminal looks like a freeze.")
            _eprint("")
            _eprint("  Check this node   : --doctor")
            _eprint("  Initialize it     : --init --domain work|personal|all")
            _eprint("  Start anyway      : --serve")
            _eprint("")
            _eprint("  Register with Claude Code:")
            _eprint(f"    claude mcp add fleet-memory -- {sys.executable} {os.path.abspath(__file__)}")
            return 2
        if _stdin_is_devnull():
            _eprint("[FAIL] stdin is the null device, so no MCP client can ever talk to")
            _eprint("       this process. Refusing to start and exit silently.")
            _eprint("       Did you mean --doctor or --init?")
            return 2

    _eprint("fleet-memory MCP server ready; waiting for JSON-RPC on stdin. Ctrl-C to stop.")
    started = time.time()
    mcp.run()
    if time.time() - started < 2.0:
        # stdin hit EOF before any client spoke: previously this exited 0 in
        # silence and looked like a successful run that had done nothing.
        _eprint("[WARN] session ended immediately - stdin closed before a client connected.")
        _eprint("       If you launched this from a shell, use --doctor instead.")
        return 2
    return 0


def _build_parser():
    import argparse
    p = argparse.ArgumentParser(
        prog="fleet_memory.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Hermes Fleet Memory - distributed vector memory over a FastMCP stdio server.",
        epilog=(
            "Typical use:\n"
            "  --doctor                      bounded health check (safe, always exits)\n"
            "  --init --domain personal      initialize this node\n"
            "  --warm                        pre-download the embedding model\n"
            "  --serve                       run the stdio server explicitly\n"
            "\n"
            "With no arguments it runs as an MCP stdio server, which is how MCP clients\n"
            "launch it. Run --doctor instead of launching it by hand."
        ),
    )
    p.add_argument("--init", action="store_true",
                   help="Initialize this node: probe Qdrant, bootstrap the collection, write .env.")
    p.add_argument("--doctor", action="store_true",
                   help="Non-destructive preflight of deps, config, connectivity and model cache.")
    p.add_argument("--bootstrap", action="store_true",
                   help="Create the Qdrant collection and payload indexes only.")
    p.add_argument("--warm", action="store_true",
                   help="Pre-download the embedding model so the first search is not slow.")
    p.add_argument("--serve", action="store_true",
                   help="Explicitly start the FastMCP stdio server (blocks on stdin).")
    p.add_argument("--domain", choices=["work", "personal", "shared", "all"],
                   help="Domain firewall for this node (sets FLEET_HARD_DOMAIN).")
    p.add_argument("--url", help="Qdrant URL, for managed/cloud clusters.")
    p.add_argument("--key", help="Qdrant API key.")
    p.add_argument("--host", help="Qdrant host (default 127.0.0.1).")
    p.add_argument("--port", type=int, help="Qdrant port (default 6333).")
    p.add_argument("--force", action="store_true", help="Overwrite an existing .env during --init.")
    p.add_argument("--version", action="version", version=f"hermes-fleet-memory {FLEET_VERSION}")
    return p


def main(argv=None) -> int:
    # Unknown flags exit 2 with usage on stderr rather than silently starting a
    # server that blocks forever -- that fall-through is what used to strand
    # agents running the documented "--init" command.
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    if args.doctor:
        return cmd_doctor(args)
    if args.warm:
        return cmd_warm(args)
    if args.init:
        send_anonymous_beacon()
        return cmd_init(args)
    if args.bootstrap:
        _apply_overrides(args)
        try:
            bootstrap_collection()
            return 0
        except Exception as e:
            _eprint(f"[FAIL] bootstrap failed: {e}")
            return 1
    return cmd_serve(args)


if __name__ == "__main__":
    sys.exit(main())
