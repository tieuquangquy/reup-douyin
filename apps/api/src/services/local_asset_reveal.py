from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import MediaAssetType
from src.models.media import MediaAsset
from src.storage.base import StorageBackend

logger = logging.getLogger(__name__)

Runner = Callable[..., object]


class LocalAssetRevealError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _ResolvedPath(Protocol):
    absolute_path: Path


def resolve_current_local_asset_path(
    db: Session,
    *,
    source_video_id: UUID,
    asset_type: MediaAssetType,
    storage: StorageBackend,
) -> Path:
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.source_video_id == source_video_id,
            MediaAsset.asset_type == asset_type,
            MediaAsset.is_current.is_(True),
        )
    )
    if asset is None:
        raise LocalAssetRevealError("ASSET_NOT_FOUND", "No current media asset is available to open.")
    if asset.storage_provider != "local":
        raise LocalAssetRevealError("NOT_LOCAL", "Only local media assets can be revealed on this workstation.")
    resolved: _ResolvedPath = storage.resolve(asset.storage_key)
    path = Path(resolved.absolute_path).resolve()
    if not path.is_file():
        raise LocalAssetRevealError("FILE_NOT_FOUND", "The downloaded media file is missing on disk.")
    return path


def reveal_local_file_in_file_manager(
    path: Path,
    *,
    runner: Runner | None = None,
) -> dict[str, bool]:
    """Open the OS file manager on the file. Never include paths in the return value."""
    run = runner or subprocess.run
    resolved = Path(path).resolve()
    if not resolved.is_file():
        # Keep operator message free of absolute path leakage.
        raise LocalAssetRevealError("FILE_NOT_FOUND", "The downloaded media file is missing on disk.")

    if os.name == "nt":
        # explorer /select,<path> highlights the file in Windows Explorer.
        run(["explorer", f"/select,{resolved}"], check=False)
    else:
        run(["xdg-open", str(resolved.parent)], check=False)

    logger.info(
        "local_asset_revealed",
        extra={"file_name": resolved.name, "parent_exists": resolved.parent.exists()},
    )
    return {"revealed": True}


def reveal_source_video_local_asset(
    db: Session,
    *,
    source_video_id: UUID,
    storage: StorageBackend,
    asset_type: MediaAssetType = MediaAssetType.SOURCE_VIDEO_RAW,
    runner: Runner | None = None,
) -> dict[str, bool | str]:
    path = resolve_current_local_asset_path(
        db,
        source_video_id=source_video_id,
        asset_type=asset_type,
        storage=storage,
    )
    reveal_local_file_in_file_manager(path, runner=runner)
    return {
        "revealed": True,
        "asset_type": asset_type.value,
        "source_video_id": str(source_video_id),
    }
