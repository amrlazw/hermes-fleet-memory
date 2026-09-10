"""Fleet Control Plane — portable configuration.

Design rules:
  * ALL state lives under FLEET_HOME (default ~/.fleet). No absolute paths.
  * Nothing node-specific, host-specific, or secret is baked into source.
  * Every knob has an env/.env override and a safe non-destructive default.

Resolution order for any value: process env -> $FLEET_HOME/.env -> default.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = Path.home() / ".fleet"

# Names that start with FLEET_KEY_ but are NOT node credentials.
_RESERVED_KEY_SUFFIXES = {"id", "rotate", "file"}


def _load_env_file(path: Path) -> dict:
    """Minimal .env reader: KEY=VALUE, '#' comments, optional surrounding quotes."""
    data: dict = {}
    if path and path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class Config:
    def __init__(self, home=None):
        self.home = Path(os.getenv("FLEET_HOME") or home or DEFAULT_HOME).expanduser()
        self.home.mkdir(parents=True, exist_ok=True)
        self.env_file = self.home / ".env"
        self.file_env = _load_env_file(self.env_file)

    # ---------------------------------------------------------------- lookup
    def get(self, name: str, default=None):
        value = os.getenv(name)
        if value not in (None, ""):
            return value
        value = self.file_env.get(name)
        if value not in (None, ""):
            return value
        return default

    def require(self, name: str, hint: str = "") -> str:
        value = self.get(name)
        if not value:
            raise SystemExit(
                f"[fleet] FATAL: {name} is not set.\n"
                f"        Define it in {self.env_file} or the environment.\n"
                f"        {hint}".rstrip()
            )
        return value

    # ----------------------------------------------------------------- paths
    @property
    def db_path(self) -> Path:
        return self.home / "tasks.db"

    @property
    def key_path(self) -> Path:
        return self.home / "fleet_ed25519.key"

    @property
    def jwks_path(self) -> Path:
        return self.home / "fleet_keys.json"

    # -------------------------------------------------------------- identity
    @property
    def node_id(self) -> str:
        return self.get("FLEET_NODE_ID", "local")

    @property
    def key_id(self) -> str:
        return self.get("FLEET_KEY_ID", f"{self.node_id}-fleet-1")

    # ---------------------------------------------------------------- server
    @property
    def host(self) -> str:
        return self.get("FLEET_HOST", "127.0.0.1")

    @property
    def port(self) -> int:
        return int(self.get("FLEET_PORT", "8088"))

    @property
    def max_pending(self) -> int:
        return int(self.get("FLEET_MAX_PENDING", "1000"))

    # ------------------------------------------------- telegram (all optional)
    @property
    def telegram_token(self) -> str:
        return self.get("TELEGRAM_BOT_TOKEN", "")

    @property
    def telegram_chat_id(self) -> str:
        return self.get("TELEGRAM_CHAT_ID", "")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    # ------------------------------------------------------------------ nodes
    @property
    def nodes(self) -> list:
        """Node registry. Defaults to just this host, so single-machine works."""
        raw = self.get("FLEET_NODES") or self.node_id
        return [n.strip() for n in raw.split(",") if n.strip()]

    @property
    def node_keys(self) -> dict:
        """{bearer token: node name} derived from FLEET_KEY_<NODE> entries."""
        merged = dict(self.file_env)
        merged.update({k: v for k, v in os.environ.items() if k.startswith("FLEET_KEY_")})
        out: dict = {}
        for name, value in merged.items():
            if not name.startswith("FLEET_KEY_") or not value:
                continue
            suffix = name[len("FLEET_KEY_"):].lower()
            if suffix in _RESERVED_KEY_SUFFIXES or suffix not in self.nodes:
                continue
            out[value] = suffix
        return out

    def describe(self) -> str:
        tg = "enabled" if self.telegram_enabled else "disabled (text/photo tasks -> 'skipped')"
        return (
            f"  FLEET_HOME : {self.home}\n"
            f"  node_id    : {self.node_id}\n"
            f"  key_id     : {self.key_id}\n"
            f"  bind       : {self.host}:{self.port}\n"
            f"  nodes      : {', '.join(self.nodes)}\n"
            f"  node keys  : {len(self.node_keys)} configured\n"
            f"  telegram   : {tg}"
        )


_cached: Config | None = None


def get_config() -> Config:
    global _cached
    if _cached is None:
        _cached = Config()
    return _cached
