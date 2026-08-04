from __future__ import annotations

from base64 import b64encode
import os
from pathlib import Path

from src.core.settings import Settings


LOCAL_APP_ENVS = frozenset({"local", "dev", "development", "test"})


class PlatformCredentialKeyStoreError(ValueError):
    pass


def resolve_platform_credential_key_ref(
    settings: Settings,
    *,
    create_local: bool = False,
) -> str | None:
    """Resolve an external key ref or a server-only local bootstrap key.

    Local key creation is explicit and only happens while an authenticated
    administrator saves integration configuration. Production never creates a
    filesystem key implicitly.
    """

    configured_ref = str(settings.platform_credential_encryption_key_ref or "").strip()
    if configured_ref:
        return configured_ref

    if str(settings.app_env or "").strip().lower() not in LOCAL_APP_ENVS:
        return None

    path = Path(settings.platform_credential_local_key_path).expanduser()
    if not path.is_absolute():
        # API and worker are commonly launched from different working directories.
        # Resolve the local bootstrap key relative to the API package so both
        # processes decrypt the same credential without requiring a cwd convention.
        path = (Path(__file__).resolve().parents[3] / path).resolve()
    existing = _read_key(path)
    if existing or not create_local:
        return existing

    path.parent.mkdir(parents=True, exist_ok=True)
    generated = "base64:" + b64encode(os.urandom(32)).decode("ascii")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = _read_key(path)
        if existing:
            return existing
        raise PlatformCredentialKeyStoreError("Local platform credential key is unreadable")
    try:
        os.write(descriptor, (generated + "\n").encode("ascii"))
    finally:
        os.close(descriptor)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows ACLs remain authoritative; the file stays under server-only
        # local data and is never served by the web application.
        pass
    return generated


def _read_key(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PlatformCredentialKeyStoreError("Local platform credential key is unreadable") from exc
    return value or None
