from __future__ import annotations

from dataclasses import dataclass

from src.enums import PublishTargetPlatform


@dataclass(frozen=True)
class PublishTargetConfig:
    platform: PublishTargetPlatform
    label: str
    caption_max_length: int
    hashtag_limit: int
    default_cta: str
    default_hashtags: tuple[str, ...]
    supports_scheduling: bool = True
    account_ref_required: bool = False


TARGET_CONFIGS: dict[PublishTargetPlatform, PublishTargetConfig] = {
    PublishTargetPlatform.TIKTOK: PublishTargetConfig(
        platform=PublishTargetPlatform.TIKTOK,
        label="TikTok",
        caption_max_length=2200,
        hashtag_limit=12,
        default_cta="Theo doi de xem them video moi.",
        default_hashtags=("vietsub", "xuhuong", "shortvideo"),
    ),
    PublishTargetPlatform.FACEBOOK_REELS: PublishTargetConfig(
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        label="Facebook Reels",
        caption_max_length=2200,
        hashtag_limit=10,
        default_cta="Luu lai va chia se neu thay huu ich.",
        default_hashtags=("reels", "vietsub", "video"),
    ),
    PublishTargetPlatform.YOUTUBE_SHORTS: PublishTargetConfig(
        platform=PublishTargetPlatform.YOUTUBE_SHORTS,
        label="YouTube Shorts",
        caption_max_length=5000,
        hashtag_limit=15,
        default_cta="Dang ky kenh de xem them Shorts moi.",
        default_hashtags=("shorts", "vietsub", "youtube"),
    ),
}


def get_target_config(platform: PublishTargetPlatform | str) -> PublishTargetConfig:
    return TARGET_CONFIGS[PublishTargetPlatform(platform)]


def list_target_configs() -> list[PublishTargetConfig]:
    return list(TARGET_CONFIGS.values())
