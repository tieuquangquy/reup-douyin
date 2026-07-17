"""Password hashing helpers (stdlib PBKDF2-HMAC-SHA256 — no extra dependency)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return an encoded password hash safe to store in the database."""
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verify against ``hash_password`` output."""
    try:
        algorithm, iterations_raw, salt, expected = encoded.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        if iterations < 1 or not salt or not expected:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("ascii"),
            iterations,
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (TypeError, ValueError, AttributeError):
        return False
