"""Credential detection for memory cards before they reach the vector store.

Every node holding the Qdrant key can read the `shared` domain, so a secret
written there is readable fleet-wide and survives any later rotation of the
original. Cards should say where a secret lives, never carry it.
"""
import re
from typing import List

# Name -> pattern. Keep patterns specific: a false positive blocks a legitimate write.
SECRET_PATTERNS = {
    # 256-bit keys as written by the wizard. Digests tagged "sha256:" are content hashes, not keys.
    "hex256_key": re.compile(r"(?<![0-9A-Fa-f])(?<!sha256:)[0-9A-Fa-f]{64}(?![0-9A-Fa-f])"),
    "fleet_bearer_token": re.compile(r"\bflk_[A-Za-z0-9_\-]{16,}"),
    "a2a_peer_token": re.compile(r"\btok_[A-Za-z0-9_\-]{16,}"),
    "cloudflare_token": re.compile(r"\bcfut_[A-Za-z0-9_\-]{16,}"),
    "api_secret_key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    "telegram_bot_token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}


def find_secrets(text: str) -> List[str]:
    """Names of the credential patterns found in text. Never returns the matched values."""
    if not text or not isinstance(text, str):
        return []
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
