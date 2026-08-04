from __future__ import annotations

from base64 import b64decode, b64encode, urlsafe_b64decode
import hashlib
import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PlatformSecretEnvelopeError(ValueError):
    pass


class PlatformSecretEnvelope:
    """AES-256-GCM boundary for platform credentials and temporary OAuth data."""

    PREFIX: Final[str] = "envelope-v1:"
    NONCE_SIZE_BYTES: Final[int] = 12
    KEY_SIZE_BYTES: Final[int] = 32

    def __init__(self, *, key_ref: str | None):
        self.key_ref = (key_ref or "").strip()

    @property
    def configured(self) -> bool:
        try:
            self._resolve_key()
        except PlatformSecretEnvelopeError:
            return False
        return True

    def encrypt(self, plaintext: str, *, context: str) -> str:
        if not plaintext:
            raise PlatformSecretEnvelopeError("Cannot encrypt an empty platform secret")
        nonce = os.urandom(self.NONCE_SIZE_BYTES)
        ciphertext = AESGCM(self._resolve_key()).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._associated_data(context),
        )
        return self.PREFIX + b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, ciphertext: str | None, *, context: str) -> str | None:
        if not ciphertext or not ciphertext.startswith(self.PREFIX):
            return None
        try:
            raw = b64decode(ciphertext.removeprefix(self.PREFIX).encode("ascii"))
            nonce = raw[: self.NONCE_SIZE_BYTES]
            encrypted = raw[self.NONCE_SIZE_BYTES :]
            if len(nonce) != self.NONCE_SIZE_BYTES or not encrypted:
                return None
            plaintext = AESGCM(self._resolve_key()).decrypt(
                nonce,
                encrypted,
                self._associated_data(context),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError, PlatformSecretEnvelopeError):
            return None

    @staticmethod
    def _associated_data(context: str) -> bytes:
        value = context.strip()
        if not value:
            raise PlatformSecretEnvelopeError("Platform secret context is required")
        return f"reup-douyin:{value}:envelope-v1".encode("utf-8")

    def _resolve_key(self) -> bytes:
        raw_ref = self.key_ref
        if not raw_ref:
            raise PlatformSecretEnvelopeError("PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF is required")

        for prefix in ("base64:", "b64:"):
            if raw_ref.startswith(prefix):
                try:
                    key = b64decode(raw_ref.removeprefix(prefix).encode("ascii"))
                except ValueError as exc:
                    raise PlatformSecretEnvelopeError("Platform credential key is not valid base64") from exc
                if len(key) != self.KEY_SIZE_BYTES:
                    raise PlatformSecretEnvelopeError("Platform credential key must decode to 32 bytes")
                return key

        if raw_ref.startswith("hex:"):
            try:
                key = bytes.fromhex(raw_ref.removeprefix("hex:"))
            except ValueError as exc:
                raise PlatformSecretEnvelopeError("Platform credential key is not valid hex") from exc
            if len(key) != self.KEY_SIZE_BYTES:
                raise PlatformSecretEnvelopeError("Platform credential key must decode to 32 bytes")
            return key

        try:
            key = urlsafe_b64decode(raw_ref + "=" * (-len(raw_ref) % 4))
            if len(key) == self.KEY_SIZE_BYTES:
                return key
        except ValueError:
            pass

        if len(raw_ref.encode("utf-8")) >= self.KEY_SIZE_BYTES:
            return hashlib.sha256(raw_ref.encode("utf-8")).digest()
        raise PlatformSecretEnvelopeError(
            "PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF must be a 32-byte base64/hex key or a passphrase of at least 32 bytes"
        )
