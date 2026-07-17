from datetime import UTC, datetime
import unittest

from src.services.douyin_metadata_normalization import (
    build_data_quality_flags,
    calculate_engagement,
    normalize_douyin_count,
    normalize_douyin_duration,
    normalize_douyin_engagement_count,
    normalize_douyin_estimated_views,
    normalize_douyin_posted,
    parse_douyin_engagement_text,
)


class DouyinMetadataNormalizationTests(unittest.TestCase):
    def test_duration_normalizes_mm_ss_hh_mm_ss_numeric_and_invalid(self) -> None:
        short = normalize_douyin_duration(raw_text="10:47")
        long = normalize_douyin_duration(raw_text="01:02:03")
        numeric = normalize_douyin_duration(seconds=0)
        invalid = normalize_douyin_duration(raw_text="not a duration")

        self.assertEqual(short.duration_seconds, 647)
        self.assertEqual(short.duration_text, "10:47")
        self.assertEqual(short.duration_parse_confidence, "high")
        self.assertEqual(long.duration_seconds, 3723)
        self.assertEqual(long.duration_text, "01:02:03")
        self.assertEqual(numeric.duration_seconds, 0)
        self.assertEqual(numeric.duration_text, "00:00")
        self.assertEqual(invalid.duration_text, "not a duration")
        self.assertIsNone(invalid.duration_seconds)
        self.assertEqual(invalid.duration_parse_confidence, "none")

    def test_estimated_views_normalizes_ranges_single_values_and_legacy_exact_count(self) -> None:
        range_value = normalize_douyin_estimated_views("9K–43K")
        large_range = normalize_douyin_estimated_views("24K-118K")
        single = normalize_douyin_estimated_views("432K")
        chinese = normalize_douyin_estimated_views("1.2万")
        exact_numeric = normalize_douyin_estimated_views(None, 1200)
        missing = normalize_douyin_estimated_views("unknown")

        self.assertEqual((range_value.estimated_views_min, range_value.estimated_views_max, range_value.estimated_views_mid), (9000, 43000, 26000))
        self.assertEqual((large_range.estimated_views_min, large_range.estimated_views_max, large_range.estimated_views_mid), (24000, 118000, 71000))
        self.assertEqual((single.estimated_views_min, single.estimated_views_max, single.estimated_views_mid), (432000, 432000, 432000))
        self.assertEqual(chinese.estimated_views_mid, 12000)
        self.assertEqual(exact_numeric.estimated_views_display, "1.2K")
        self.assertEqual(exact_numeric.estimated_views_mid, 1200)
        self.assertIsNone(missing.estimated_views_mid)
        self.assertEqual(missing.estimated_views_parse_confidence, "none")

    def test_count_normalizes_compact_chinese_labeled_and_missing_values(self) -> None:
        self.assertEqual(normalize_douyin_count("9K"), 9000)
        self.assertEqual(normalize_douyin_count("1.5M views"), 1500000)
        self.assertEqual(normalize_douyin_count("2.4万赞"), 24000)
        self.assertEqual(normalize_douyin_count(321), 321)
        self.assertIsNone(normalize_douyin_count("--"))

    def test_posted_normalization_preserves_display_ready_fields_and_source(self) -> None:
        posted_at = datetime(2026, 4, 28, 0, 0, tzinfo=UTC)
        normalized = normalize_douyin_posted(
            posted_at=posted_at,
            posted_text="28/04/2026",
            posted_text_raw="2026年4月28日",
            posted_display="28/04/2026",
            posted_source="modal_author_row_profile_link",
        )
        raw_only = normalize_douyin_posted(posted_at=None, posted_text="很久以前", posted_text_raw=None, posted_display=None, posted_source="profile_card")

        self.assertEqual(normalized.posted_text_raw, "2026年4月28日")
        self.assertEqual(normalized.posted_text, "28/04/2026")
        self.assertEqual(normalized.posted_display, "28/04/2026")
        self.assertEqual(normalized.posted_source, "modal_author_row_profile_link")
        self.assertEqual(normalized.posted_parse_confidence, "high")
        self.assertEqual(raw_only.posted_text, "很久以前")
        self.assertEqual(raw_only.posted_parse_confidence, "low")

    def test_engagement_uses_estimated_views_mid_then_legacy_view_count_ratio(self) -> None:
        estimated = calculate_engagement(like_count=100, comment_count=20, share_count=10, favorite_count=5, estimated_views_mid=9000, view_count=10000)
        legacy = calculate_engagement(like_count=100, comment_count=20, share_count=10, favorite_count=None, estimated_views_mid=None, view_count=10000)
        missing_basis = calculate_engagement(like_count=100, comment_count=None, share_count=None, favorite_count=None, estimated_views_mid=None, view_count=None)

        self.assertEqual(estimated.engagement_score, 135)
        self.assertEqual(estimated.engagement_rate, 0.015)
        self.assertEqual(estimated.engagement_rate_basis, "estimated_views_mid")
        self.assertEqual(legacy.engagement_rate, 0.013)
        self.assertEqual(legacy.engagement_rate_basis, "view_count")
        self.assertEqual(missing_basis.engagement_score, 100)
        self.assertIsNone(missing_basis.engagement_rate)
        self.assertEqual(missing_basis.engagement_rate_basis, "none")

    def test_engagement_zero_sentinels_parse_comment_and_share_labels(self) -> None:
        comment = parse_douyin_engagement_text("comment", "抢首评")
        share = parse_douyin_engagement_text("share", "分享", share_icon_context=True)
        share_without_context = parse_douyin_engagement_text("share", "分享")

        self.assertEqual(comment.kind, "zero_sentinel")
        self.assertEqual(comment.value, 0)
        self.assertEqual(share.kind, "zero_sentinel")
        self.assertEqual(share.value, 0)
        self.assertEqual(share_without_context.kind, "missing")
        self.assertEqual(normalize_douyin_engagement_count("comment", None, "抢首评"), 0)
        self.assertEqual(normalize_douyin_engagement_count("share", None, "分享", share_icon_context=True), 0)

    def test_data_quality_flags_accept_share_count_text_like_comments(self) -> None:
        flags = build_data_quality_flags(
            thumbnail_url="https://example.test/thumb.jpg",
            preview_url=None,
            posted_at=datetime(2026, 4, 28, tzinfo=UTC),
            posted_text=None,
            duration_seconds=12,
            duration_text=None,
            estimated_views_mid=1000,
            view_count=None,
            view_count_text=None,
            like_count=10,
            like_count_text=None,
            comment_count=None,
            comment_count_text="抢首评",
            share_count=None,
            share_count_text="分享",
        )

        self.assertTrue(flags.has_comments)
        self.assertTrue(flags.has_shares)
        self.assertTrue(flags.has_all_core_metadata)

    def test_data_quality_flags_report_present_and_missing_core_metadata(self) -> None:
        complete = build_data_quality_flags(
            thumbnail_url="https://example.test/thumb.jpg",
            preview_url=None,
            posted_at=datetime(2026, 4, 28, tzinfo=UTC),
            posted_text=None,
            duration_seconds=647,
            duration_text=None,
            estimated_views_mid=26000,
            view_count=None,
            view_count_text=None,
            like_count=100,
            like_count_text=None,
            comment_count=20,
            comment_count_text=None,
            share_count=10,
        )
        partial = build_data_quality_flags(
            thumbnail_url=None,
            preview_url=None,
            posted_at=None,
            posted_text="28/04/2026",
            duration_seconds=None,
            duration_text=None,
            estimated_views_mid=None,
            view_count=None,
            view_count_text=None,
            like_count=None,
            like_count_text="1K",
            comment_count=None,
            comment_count_text=None,
            share_count=None,
        )

        self.assertTrue(complete.has_all_core_metadata)
        self.assertEqual(complete.missing_metadata_fields, [])
        self.assertFalse(partial.has_all_core_metadata)
        self.assertEqual(partial.missing_metadata_fields, ["thumbnail", "duration", "views", "comments", "shares"])


if __name__ == "__main__":
    unittest.main()
