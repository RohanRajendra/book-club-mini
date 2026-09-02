"""Hashing and checking the one shared passphrase.

PBKDF2-HMAC-SHA256 from the standard library. bcrypt or argon2 would be a
better choice against an attacker holding the hash — but nobody holds this
hash: it lives in a deployment's environment, and anyone who can read it can
read the Notion token sitting beside it, which is worth far more. What the
hashing actually buys is that the passphrase is not sitting in plaintext in a
dashboard, a shell history, or a screenshot.

The real protection is entropy. `scripts/make_secrets.py` generates a six-word
passphrase rather than inviting someone to choose one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"

#: Deliberately high for a value verified at most a handful of times a day, and
#: cheap enough not to matter on a cold start.
ITERATIONS = 600_000

SALT_BYTES = 16


def hash_passphrase(
    passphrase: str, *, salt: bytes | None = None, iterations: int = ITERATIONS
) -> str:
    """`pbkdf2_sha256$<iterations>$<salt>$<hash>`, safe to store.

    The cost factor travels inside the hash, so raising `ITERATIONS` later
    strengthens new hashes without invalidating the one already deployed.
    """
    salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    derived = _derive(passphrase, salt, iterations)
    return f"{ALGORITHM}${iterations}${_encode(salt)}${_encode(derived)}"


def verify_passphrase(passphrase: str, stored: str) -> bool:
    """Constant-time check against a stored hash. False for anything malformed.

    A malformed hash is a misconfigured deployment, and the safe reading of
    "I cannot tell" is "no".
    """
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        derived = _derive(passphrase, _decode(salt), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(derived, _decode(expected))


def _derive(passphrase: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations)


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
