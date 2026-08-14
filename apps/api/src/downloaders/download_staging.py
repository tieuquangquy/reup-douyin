from __future__ import annotations

import re
import time
from pathlib import Path

from src.core.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[4]


def download_staging_root() -> Path:
    settings = get_settings()
    override = getattr(settings, "douyin_download_staging_dir", None) or getattr(
        settings,
        "douyin_playwright_download_staging_dir",
        None,
    )
    if isinstance(override, str) and override.strip():
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / ".douyin_profiles" / "download_staging_v2").resolve()


def staging_directory(
    *,
    aweme_id: str,
    workspace_id: object | None = None,
    account_connection_id: object | None = None,
    transfer_id: object | None = None,
) -> Path:
    root = download_staging_root()
    parts = (
        _safe_part(workspace_id, fallback="workspace-unknown"),
        _safe_part(account_connection_id, fallback="account-default"),
        _safe_part(aweme_id, fallback="aweme-unknown"),
        _safe_part(transfer_id, fallback="transfer-default"),
    )
    path = root.joinpath(*parts).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Download staging path escapes configured root") from exc
    path.mkdir(parents=True, exist_ok=True)
    return path


def staging_path(
    *,
    aweme_id: str,
    workspace_id: object | None = None,
    account_connection_id: object | None = None,
    transfer_id: object | None = None,
    extension: str = "mp4",
    stem: str = "video",
) -> Path:
    safe_extension = re.sub(r"[^0-9A-Za-z]", "", extension).lower() or "mp4"
    safe_stem = _safe_part(stem, fallback="video")
    return staging_directory(
        aweme_id=aweme_id,
        workspace_id=workspace_id,
        account_connection_id=account_connection_id,
        transfer_id=transfer_id,
    ) / f"{safe_stem}.{safe_extension}"


def is_managed_staging_path(path: str | Path) -> bool:
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(download_staging_root())
    except ValueError:
        return False
    return True


def cleanup_stale_staging(*, ttl_seconds: float = 86_400, now: float | None = None) -> int:
    """Delete only expired, non-authoritative staging artifacts and return bytes freed."""
    cutoff = (time.time() if now is None else float(now)) - max(300.0, float(ttl_seconds))
    root = download_staging_root()
    if not root.exists():
        return 0
    freed = 0
    files = [path for path in root.rglob("*") if path.is_file()]
    for path in files:
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            size = path.stat().st_size
            path.unlink()
            freed += size
        except OSError:
            continue
    # Remove empty namespace directories bottom-up; never recursively delete a directory.
    for directory in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return freed


def _safe_part(value: object | None, *, fallback: str) -> str:
    raw = str(value or "").strip()
    cleaned = re.sub(r"[^0-9A-Za-z_-]", "", raw)
    return cleaned[:128] or fallback
