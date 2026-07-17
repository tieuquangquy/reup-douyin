from __future__ import annotations

from dataclasses import dataclass

from src.services.candidate_types import FilterConfig, FilterDateMode, FilterSortOption, ScoreWeights, TextDensity


@dataclass(frozen=True)
class FilterPreset:
    name: str
    description: str
    use_when: str
    filter_config: FilterConfig
    score_weights: ScoreWeights


PRESETS: dict[str, FilterPreset] = {
    "viral_discovery": FilterPreset(
        name="viral_discovery",
        description="Find recent videos with strong engagement and enough views to justify review.",
        use_when="Use after profile ingest to quickly find likely viral candidates.",
        filter_config=FilterConfig(
            date_mode=FilterDateMode.LAST_N_DAYS,
            n_days=45,
            min_views=10_000,
            min_like_rate=0.025,
            min_share_rate=0.002,
            min_duration_seconds=6,
            max_duration_seconds=120,
            max_text_density=TextDensity.HIGH,
            sort=FilterSortOption.SCORE_DESC,
            limit=50,
        ),
        score_weights=ScoreWeights(
            engagement_quality=0.26,
            freshness=0.18,
            views_normalized=0.18,
            like_rate=0.14,
            comment_share_quality=0.14,
            duration_fit=0.06,
            speech_bonus=0.02,
            text_complexity_penalty=0.01,
            watermark_penalty=0.005,
            copyright_risk_penalty=0.005,
        ),
    ),
    "safe_reup": FilterPreset(
        name="safe_reup",
        description="Prioritize videos that are easier to process and lower risk.",
        use_when="Use before download/review when operator wants fewer editing surprises.",
        filter_config=FilterConfig(
            date_mode=FilterDateMode.LAST_N_DAYS,
            n_days=120,
            min_views=3_000,
            min_like_rate=0.015,
            min_duration_seconds=8,
            max_duration_seconds=75,
            allow_no_speech=False,
            require_speech=True,
            max_text_density=TextDensity.MEDIUM,
            exclude_heavy_watermark=True,
            exclude_high_copyright_risk=True,
            exclude_high_processing_complexity=True,
            sort=FilterSortOption.SCORE_DESC,
            limit=50,
        ),
        score_weights=ScoreWeights(
            engagement_quality=0.18,
            freshness=0.10,
            views_normalized=0.10,
            like_rate=0.10,
            comment_share_quality=0.08,
            duration_fit=0.16,
            speech_bonus=0.12,
            text_complexity_penalty=0.08,
            watermark_penalty=0.04,
            copyright_risk_penalty=0.04,
        ),
    ),
    "affiliate_priority": FilterPreset(
        name="affiliate_priority",
        description="Favor medium-length, easy-to-localize videos with conversion potential.",
        use_when="Use for product/affiliate style review queues.",
        filter_config=FilterConfig(
            date_mode=FilterDateMode.LAST_N_DAYS,
            n_days=90,
            min_views=5_000,
            min_like_rate=0.018,
            min_comment_rate=0.001,
            min_duration_seconds=15,
            max_duration_seconds=90,
            max_text_density=TextDensity.MEDIUM,
            exclude_slideshow=True,
            exclude_heavy_watermark=True,
            exclude_high_copyright_risk=True,
            sort=FilterSortOption.SCORE_DESC,
            limit=50,
        ),
        score_weights=ScoreWeights(
            engagement_quality=0.18,
            freshness=0.12,
            views_normalized=0.12,
            like_rate=0.12,
            comment_share_quality=0.14,
            duration_fit=0.16,
            speech_bonus=0.08,
            text_complexity_penalty=0.04,
            watermark_penalty=0.02,
            copyright_risk_penalty=0.02,
        ),
    ),
}


def list_presets() -> list[FilterPreset]:
    return list(PRESETS.values())


def get_preset(name: str) -> FilterPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown filter preset: {name}") from exc


def resolve_filter_config(
    *,
    preset_name: str | None = None,
    override_config: FilterConfig | None = None,
) -> tuple[FilterConfig, ScoreWeights, str | None]:
    if preset_name is None:
        return override_config or FilterConfig(), ScoreWeights(), None

    preset = get_preset(preset_name)
    if override_config is None:
        return preset.filter_config, preset.score_weights, preset.name

    base = preset.filter_config.to_dict()
    overrides = {key: value for key, value in override_config.to_dict().items() if value is not None}
    merged = {**base, **overrides}
    return filter_config_from_dict(merged), preset.score_weights, preset.name


def filter_config_from_dict(data: dict) -> FilterConfig:
    parsed = dict(data)
    if parsed.get("date_mode") is not None:
        parsed["date_mode"] = FilterDateMode(parsed["date_mode"])
    if parsed.get("sort") is not None:
        parsed["sort"] = FilterSortOption(parsed["sort"])
    if parsed.get("max_text_density") is not None:
        parsed["max_text_density"] = TextDensity(parsed["max_text_density"])
    return FilterConfig(**parsed)

