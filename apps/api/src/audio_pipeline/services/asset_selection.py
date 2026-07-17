from __future__ import annotations

from typing import Any

from src.enums import MediaAssetStatus, MediaAssetType


AUDIO_INPUT_PRIORITY = (
    MediaAssetType.SOURCE_AUDIO_EXTRACT,
    MediaAssetType.SOURCE_VIDEO_RAW,
)


def choose_audio_input_asset(assets: list[Any]) -> Any | None:
    current_available = [
        asset
        for asset in assets
        if getattr(asset, "is_current", False)
        and getattr(asset, "status", None) == MediaAssetStatus.AVAILABLE
    ]
    for asset_type in AUDIO_INPUT_PRIORITY:
        for asset in current_available:
            if getattr(asset, "asset_type", None) == asset_type:
                return asset
    return None
