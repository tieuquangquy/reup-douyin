"""Shared Download Video quality and provenance policy.

The downloader has several resolver implementations (yt-dlp, Playwright and
direct HTTP).  This module keeps the small pieces of policy that must agree
across all of them in one place.  It is deliberately dependency-light so it
can also be used by cache validation and operator telemetry.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any


class WatermarkAuthority(StrEnum):
    """Evidence level for the absence/presence of a platform watermark."""

    VERIFIED_PLAYBACK_PROVENANCE = "verified_playback_provenance"
    VERIFIED_YTDLP_PROVENANCE = "verified_ytdlp_provenance"
    EXPLICIT_WATERMARKED = "explicit_watermarked"
    URL_HINT_ONLY = "url_hint_only"
    UNKNOWN = "unknown"


class DownloadQualityProfile(StrEnum):
    """Supported source-selection policies.

    ``balanced_processing`` is the Phase 1 default: it keeps the source
    compatible with the local OCR/render stack. ``source_master`` is exposed
    for the later dual-artifact flow and never becomes the silent default.
    """

    BALANCED_PROCESSING = "balanced_processing"
    SOURCE_MASTER = "source_master"


DOWNLOAD_POLICY_VERSION = "download-quality-policy-v2"


def is_verified_no_logo(
    *,
    watermark_free: bool | None,
    watermark_authority: str | None,
) -> bool:
    """Return true only for affirmative resolver provenance.

    The boolean remains for backwards-compatible asset metadata.  New runtime
    resolvers must provide an authority; a legacy ``True`` is accepted only as
    a compatibility bridge for injected/test adapters and is never inferred
    from a missing value.
    """

    authority = str(watermark_authority or "").strip().lower()
    if authority in {
        WatermarkAuthority.VERIFIED_PLAYBACK_PROVENANCE.value,
        WatermarkAuthority.VERIFIED_YTDLP_PROVENANCE.value,
    }:
        return watermark_free is True
    return watermark_free is True and authority == "legacy_explicit_true"


def policy_fingerprint(
    *,
    profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value,
    target_long_edge: int = 1920,
    allow_watermarked_fallback: bool = False,
    max_bytes: int = 2_000_000_000,
    selector: str | None = None,
) -> str:
    """Content fingerprint for the rules that decide SOURCE_VIDEO_RAW quality."""

    payload: dict[str, Any] = {
        "policy_version": DOWNLOAD_POLICY_VERSION,
        "profile": str(profile or DownloadQualityProfile.BALANCED_PROCESSING.value),
        "target_long_edge": max(1, int(target_long_edge)),
        "allow_watermarked_fallback": bool(allow_watermarked_fallback),
        "max_bytes": max(1, int(max_bytes)),
        "selector": str(selector or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def quality_policy_metadata(
    *,
    profile: str,
    target_long_edge: int,
    allow_watermarked_fallback: bool,
    max_bytes: int,
    selector: str | None,
) -> dict[str, Any]:
    return {
        "policy_version": DOWNLOAD_POLICY_VERSION,
        "profile": str(profile),
        "target_long_edge": max(1, int(target_long_edge)),
        "allow_watermarked_fallback": bool(allow_watermarked_fallback),
        "max_bytes": max(1, int(max_bytes)),
        "selector": str(selector or "").strip(),
        "fingerprint": policy_fingerprint(
            profile=profile,
            target_long_edge=target_long_edge,
            allow_watermarked_fallback=allow_watermarked_fallback,
            max_bytes=max_bytes,
            selector=selector,
        ),
    }




def current_quality_policy(settings: object) -> dict[str, Any]:
    """Build the active policy without leaking Settings into downloader models."""

    profile = str(
        getattr(settings, "douyin_download_quality_profile", DownloadQualityProfile.BALANCED_PROCESSING.value)
        or DownloadQualityProfile.BALANCED_PROCESSING.value
    ).strip().lower()
    if profile not in {item.value for item in DownloadQualityProfile}:
        profile = DownloadQualityProfile.BALANCED_PROCESSING.value
    try:
        target_long_edge = int(getattr(settings, "douyin_download_target_long_edge", 1920) or 1920)
    except (TypeError, ValueError):
        target_long_edge = 1920
    try:
        max_bytes = int(getattr(settings, "douyin_download_max_bytes", 2_000_000_000) or 2_000_000_000)
    except (TypeError, ValueError):
        max_bytes = 2_000_000_000
    return quality_policy_metadata(
        profile=profile,
        target_long_edge=max(1, target_long_edge),
        allow_watermarked_fallback=bool(
            getattr(settings, "douyin_download_allow_watermarked_fallback", False)
        ),
        max_bytes=max(1, max_bytes),
        selector=str(getattr(settings, "douyin_yt_dlp_format", "") or ""),
    )
