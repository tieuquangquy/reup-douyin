from src.adapters.types import NormalizedSourceProfile, NormalizedSourceVideo
from src.enums import SourcePlatformEnum


def source_profile_dedupe_key(
    source_platform: SourcePlatformEnum,
    source_profile_external_id: str,
) -> tuple[SourcePlatformEnum, str]:
    return source_platform, source_profile_external_id


def source_video_dedupe_key(
    source_platform: SourcePlatformEnum,
    source_video_external_id: str,
) -> tuple[SourcePlatformEnum, str]:
    return source_platform, source_video_external_id


def normalized_profile_dedupe_key(profile: NormalizedSourceProfile) -> tuple[SourcePlatformEnum, str]:
    return source_profile_dedupe_key(profile.source_platform, profile.source_profile_external_id)


def normalized_video_dedupe_key(video: NormalizedSourceVideo) -> tuple[SourcePlatformEnum, str]:
    return source_video_dedupe_key(video.source_platform, video.source_video_external_id)

