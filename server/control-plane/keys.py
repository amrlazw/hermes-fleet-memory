"""Ed25519 receipt signing keys — generated on first run, never shipped.

A first-run user gets a working keypair instead of a crash loop; the private
key is written 0600 under FLEET_HOME and the public half is published as a
JWKS document so any peer can verify receipts independently.
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def ensure_keys(cfg, force: bool = False):
    """Return (private_key, public_key, generated_flag)."""
    generated = False

    if force or not cfg.key_path.exists():
        private = ed25519.Ed25519PrivateKey.generate()
        cfg.key_path.write_bytes(
            private.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        try:
            os.chmod(cfg.key_path, 0o600)
        except OSError:
            pass  # best-effort on Windows / exotic filesystems
        generated = True

    private = ed25519.Ed25519PrivateKey.from_private_bytes(cfg.key_path.read_bytes())
    public = private.public_key()

    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": cfg.key_id,
                "use": "sig",
                "alg": "EdDSA",
                "x": b64u(
                    public.public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw,
                    )
                ),
            }
        ]
    }
    cfg.jwks_path.write_text(json.dumps(jwks, indent=2) + "\n", encoding="utf-8")

    return private, public, generated


def load_public_key_from_jwks(jwks: dict, kid: str | None = None):
    """Extract an Ed25519 public key from a JWKS document.

    Accepts both standard base64url 'x' (RFC 7518) and legacy hex-encoded 'x',
    so receipts issued before the format was standardised still verify.
    """
    for entry in jwks.get("keys", []):
        if kid and entry.get("kid") != kid:
            continue

        x = entry.get("x", "")
        try:
            if len(x) == 64 and all(c in "0123456789abcdefABCDEF" for c in x):
                raw = bytes.fromhex(x)
            else:
                raw = base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
        except Exception as exc:
            raise ValueError(f"Unreadable key material for kid={entry.get('kid')!r}: {exc}") from exc

        return ed25519.Ed25519PublicKey.from_public_bytes(raw)

    raise KeyError(f"No Ed25519 key found for kid={kid!r}")
