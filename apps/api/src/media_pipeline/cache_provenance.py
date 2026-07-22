"""Content identity helpers for media-derived caches."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def video_content_fingerprint(video_path: str | Path) -> str:
    path = Path(video_path)
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    chunk_size = 1024 * 1024
    with path.open("rb") as handle:
        digest.update(handle.read(chunk_size))
        if size > chunk_size:
            handle.seek(max(0, size - chunk_size))
            digest.update(handle.read(chunk_size))
    return digest.hexdigest()


def position_cache_matches_video(
    payload: dict[str, Any],
    video_path: str | Path,
) -> bool:
    expected = str(payload.get("video_fingerprint") or "").strip()
    return bool(expected) and expected == video_content_fingerprint(video_path)
