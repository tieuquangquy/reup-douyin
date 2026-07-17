from __future__ import annotations

from typing import Any

from src.services.publish_targets import PublishTargetConfig, get_target_config


def generate_initial_publish_payload(source_video: Any, config: PublishTargetConfig) -> dict:
    caption_source = (source_video.caption or "").strip()
    title = _truncate(caption_source or source_video.source_video_external_id, 120)
    caption = _truncate(caption_source or "Video moi da Viet hoa, san sang chia se.", 180)
    hashtags = [{"tag": tag, "source": "platform_default"} for tag in config.default_hashtags]
    if source_video.source_profile and source_video.source_profile.display_name:
        hashtags.append({"tag": _hashtag_slug(source_video.source_profile.display_name), "source": "source_profile"})
    return {
        "title": title,
        "caption": caption,
        "cta_text": config.default_cta,
        "hashtags": hashtags[: config.hashtag_limit],
    }


def validate_publish_draft_payload(draft: Any) -> list[str]:
    errors: list[str] = []
    if not draft.target_platform:
        errors.append("target_platform is required")
    if not (draft.caption or "").strip():
        errors.append("caption is required")
    if not (draft.cta_text or "").strip():
        errors.append("cta_text is required")
    hashtags = draft.hashtags_json or []
    if len(hashtags) == 0:
        errors.append("at least one hashtag is required")
    if draft.target_platform:
        config = get_target_config(draft.target_platform)
        if len(hashtags) > config.hashtag_limit:
            errors.append(f"hashtags exceed limit for {config.platform}: {config.hashtag_limit}")
        if len((draft.caption or "") + " " + (draft.cta_text or "")) > config.caption_max_length:
            errors.append(f"caption plus CTA exceed platform limit: {config.caption_max_length}")
    return errors


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[: max_length - 1].rstrip() + "..."


def _hashtag_slug(value: str) -> str:
    return "".join(ch for ch in value.lower().replace(" ", "") if ch.isalnum())[:40] or "video"
