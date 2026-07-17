from datetime import UTC, datetime, timedelta
import unittest

from src.enums import RiskFlagType, RiskSeverity
from src.services.candidate_filter import apply_candidate_filter
from src.services.candidate_types import (
    CandidateSourceRecord,
    ContentSignals,
    FilterConfig,
    FilterDateMode,
    FilterSortOption,
    MetricSnapshotInput,
    RiskFlagInput,
    TextDensity,
)
from src.services.filter_presets import get_preset, resolve_filter_config
from src.services.reup_score import REUP_SCORE_V1, calculate_reup_score_v1


NOW = datetime(2026, 4, 17, tzinfo=UTC)


def record(
    key: str,
    *,
    days_old: int,
    views: int,
    likes: int,
    comments: int = 0,
    shares: int = 0,
    duration: float = 30,
    has_speech: bool | None = True,
    text_density: TextDensity | None = TextDensity.LOW,
    heavy_watermark: bool | None = False,
    copyright_high: bool = False,
) -> CandidateSourceRecord:
    return CandidateSourceRecord(
        source_video_id=key,
        source_profile_id="profile-1",
        source_video_external_id=key,
        source_url=f"https://example.test/{key}",
        caption=f"video {key}",
        posted_at=NOW - timedelta(days=days_old),
        duration_seconds=duration,
        metrics=MetricSnapshotInput(
            view_count=views,
            like_count=likes,
            comment_count=comments,
            share_count=shares,
        ),
        content_signals=ContentSignals(
            has_speech=has_speech,
            text_density=text_density,
            has_heavy_watermark=heavy_watermark,
        ),
        risk_flags=[
            RiskFlagInput(RiskFlagType.COPYRIGHT, RiskSeverity.HIGH)
        ]
        if copyright_high
        else [],
    )


class CandidateFilterScoreTests(unittest.TestCase):
    def test_filter_config_validation(self) -> None:
        with self.assertRaises(ValueError):
            FilterConfig(date_mode=FilterDateMode.LAST_N_DAYS)
        with self.assertRaises(ValueError):
            FilterConfig(date_mode=FilterDateMode.LATEST_N_VIDEOS, n_videos=0)

    def test_last_n_days_filter(self) -> None:
        result = apply_candidate_filter(
            [
                record("fresh", days_old=5, views=10_000, likes=800),
                record("old", days_old=100, views=50_000, likes=4_000),
            ],
            FilterConfig(date_mode=FilterDateMode.LAST_N_DAYS, n_days=30),
            now=NOW,
        )
        self.assertEqual(result.total_count, 2)
        self.assertEqual(len(result.evaluations), 1)
        self.assertEqual(result.evaluations[0].record.source_video_external_id, "fresh")

    def test_latest_n_videos_filter(self) -> None:
        result = apply_candidate_filter(
            [
                record("a", days_old=3, views=10_000, likes=500),
                record("b", days_old=1, views=10_000, likes=500),
                record("c", days_old=2, views=10_000, likes=500),
            ],
            FilterConfig(date_mode=FilterDateMode.LATEST_N_VIDEOS, n_videos=2, sort=FilterSortOption.NEWEST_FIRST),
            now=NOW,
        )
        self.assertEqual([item.record.source_video_external_id for item in result.evaluations], ["b", "c"])

    def test_metric_and_ratio_filtering(self) -> None:
        result = apply_candidate_filter(
            [
                record("strong", days_old=2, views=20_000, likes=1_200, shares=100),
                record("weak", days_old=2, views=20_000, likes=100, shares=5),
            ],
            FilterConfig(min_views=10_000, min_like_rate=0.03, min_share_rate=0.002),
            now=NOW,
        )
        matched = [item for item in result.evaluations if item.matched]
        rejected = [item for item in result.evaluations if not item.matched]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].record.source_video_external_id, "strong")
        self.assertIn("like_rate_below_min", rejected[0].exclusion_reasons)

    def test_aggregate_engagement_rate_filtering(self) -> None:
        result = apply_candidate_filter(
            [
                record("strong", days_old=2, views=10_000, likes=700, comments=100, shares=100),
                record("weak", days_old=2, views=10_000, likes=100, comments=20, shares=10),
            ],
            FilterConfig(min_engagement_rate=0.05, max_engagement_rate=0.12),
            now=NOW,
        )
        matched = [item for item in result.evaluations if item.matched]
        rejected = [item for item in result.evaluations if not item.matched]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].record.source_video_external_id, "strong")
        self.assertIn("engagement_rate_below_min", rejected[0].exclusion_reasons)

    def test_has_speech_filtering(self) -> None:
        result = apply_candidate_filter(
            [
                record("speech", days_old=2, views=10_000, likes=500, has_speech=True),
                record("silent", days_old=2, views=10_000, likes=500, has_speech=False),
            ],
            FilterConfig(has_speech=False),
            now=NOW,
        )
        matched = [item for item in result.evaluations if item.matched]
        rejected = [item for item in result.evaluations if not item.matched]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].record.source_video_external_id, "silent")
        self.assertIn("speech_excluded", rejected[0].exclusion_reasons)

    def test_exclusion_flags(self) -> None:
        result = apply_candidate_filter(
            [
                record("clean", days_old=2, views=20_000, likes=1_000),
                record("wm", days_old=2, views=20_000, likes=1_000, heavy_watermark=True),
                record("risk", days_old=2, views=20_000, likes=1_000, copyright_high=True),
            ],
            FilterConfig(),
            now=NOW,
        )
        rejected_reasons = {reason for item in result.evaluations for reason in item.exclusion_reasons}
        self.assertIn("heavy_watermark_excluded", rejected_reasons)
        self.assertIn("high_copyright_risk", rejected_reasons)

    def test_preset_resolution(self) -> None:
        preset = get_preset("viral_discovery")
        config, weights, name = resolve_filter_config(preset_name="viral_discovery")
        self.assertEqual(name, preset.name)
        self.assertEqual(config.min_views, 10_000)
        self.assertGreater(weights.engagement_quality, 0)

    def test_score_breakdown_is_deterministic(self) -> None:
        source = record("score", days_old=3, views=100_000, likes=7_000, comments=300, shares=400)
        score = calculate_reup_score_v1(source, now=NOW)
        self.assertEqual(score.score_version, REUP_SCORE_V1)
        self.assertGreaterEqual(score.total_score, 75)
        self.assertEqual(score.score_label, "hot")
        self.assertIn("engagement_quality", score.breakdown)
        component = score.breakdown["engagement_quality"]
        self.assertIn("views", component.raw_input)
        self.assertGreater(component.weighted_contribution, 0)


if __name__ == "__main__":
    unittest.main()
