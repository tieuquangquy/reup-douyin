from __future__ import annotations

from base64 import b64decode, b64encode, urlsafe_b64decode
import hashlib
import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DouyinSessionSecretEnvelope:
    """Centralized Douyin session secret envelope boundary.

    `local-v1` is retained only for backwards-compatible local development data.
    It is base64 obfuscation, not encryption.

    `envelope-v1` uses AES-256-GCM with key material supplied by
    `Settings.douyin_secret_encryption_key_ref`. Phase 1 accepts a local key
    reference directly from environment configuration; production deployments
    should map this reference to KMS/HSM/provider-managed key material without
    changing service callers.
    """

    LOCAL_PREFIX: Final[str] = "local-v1:"
    ENVELOPE_PREFIX: Final[str] = "envelope-v1:"
    NONCE_SIZE_BYTES: Final[int] = 12
    KEY_SIZE_BYTES: Final[int] = 32

    def __init__(self, *, key_ref: str | None):
        self.key_ref = key_ref

    def encrypt(self, plaintext: str) -> str:
        if self.key_ref:
            return self._encrypt_envelope(plaintext)
        return self.LOCAL_PREFIX + b64encode(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        if ciphertext.startswith(self.ENVELOPE_PREFIX):
            return self._decrypt_envelope(ciphertext)
        if not ciphertext.startswith(self.LOCAL_PREFIX):
            return ciphertext
        try:
            return b64decode(ciphertext.removeprefix(self.LOCAL_PREFIX).encode("ascii")).decode("utf-8")
        except Exception:
            return None

    def _encrypt_envelope(self, plaintext: str) -> str:
        key = self._resolve_aes256_key()
        nonce = os.urandom(self.NONCE_SIZE_BYTES)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), self._associated_data())
        payload = b64encode(nonce + ciphertext).decode("ascii")
        return f"{self.ENVELOPE_PREFIX}{payload}"

    def _decrypt_envelope(self, ciphertext: str) -> str | None:
        key = self._resolve_aes256_key()
        payload = ciphertext.removeprefix(self.ENVELOPE_PREFIX)
        try:
            raw = b64decode(payload.encode("ascii"))
            nonce = raw[: self.NONCE_SIZE_BYTES]
            encrypted = raw[self.NONCE_SIZE_BYTES :]
            if len(nonce) != self.NONCE_SIZE_BYTES or not encrypted:
                return None
            plaintext = AESGCM(key).decrypt(nonce, encrypted, self._associated_data())
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            return None

    def _associated_data(self) -> bytes:
        return b"reup-douyin:douyin-session-secret:envelope-v1"

    def _resolve_aes256_key(self) -> bytes:
        if not self.key_ref:
            raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF is required for envelope encryption")
        raw_ref = self.key_ref.strip()
        if not raw_ref:
            raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF must not be empty")

        for prefix in ("base64:", "b64:"):
            if raw_ref.startswith(prefix):
                key = b64decode(raw_ref.removeprefix(prefix).encode("ascii"))
                if len(key) != self.KEY_SIZE_BYTES:
                    raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF base64 key must decode to 32 bytes")
                return key

        if raw_ref.startswith("hex:"):
            key = bytes.fromhex(raw_ref.removeprefix("hex:"))
            if len(key) != self.KEY_SIZE_BYTES:
                raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF hex key must decode to 32 bytes")
            return key

        try:
            key = urlsafe_b64decode(raw_ref + "=" * (-len(raw_ref) % 4))
            if len(key) == self.KEY_SIZE_BYTES:
                return key
        except Exception:
            pass

        if len(raw_ref.encode("utf-8")) >= self.KEY_SIZE_BYTES:
            return hashlib.sha256(raw_ref.encode("utf-8")).digest()

        raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF must be a 32-byte base64/hex key or a passphrase of at least 32 bytes")
