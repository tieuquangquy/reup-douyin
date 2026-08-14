from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
import unittest

from src.enums import CandidateStatus
from src.api.routes.capture_inbox import _promotion_raw_detail
from src.schemas.candidates import CandidateDetailResponse, CandidateListResponse
from src.services.candidate_service import CandidateEvaluationService
from src.services.capture_inbox_service import getCaptureInboxPostedDisplayExact


class FakeScalarResult(list):
    def unique(self):
        return self


class FakeHydrationDb:
    def __init__(self, item=None):
        self.item = item
        self.flushed = False

    def scalar(self, stmt):
        return self.item

    def scalars(self, stmt):
        return FakeScalarResult([])

    def flush(self):
        self.flushed = True


class Phase22FReviewCandidateContractTests(unittest.TestCase):
    def _source_video(self, *, external_id="7420000000000000001", source_url=None, metadata=None):
        return SimpleNamespace(
            id=uuid4(),
            source_profile_id=uuid4(),
            source_video_external_id=external_id,
            source_url=source_url or f"https://www.douyin.com/video/{external_id}",
            caption="Fixture",
            posted_at=None,
            duration_seconds=None,
            metadata_json=metadata or {},
            raw_payload_json={},
        )

    def _candidate(self, *, metadata=None, status=CandidateStatus.SHORTLISTED, score=55.0, source_video=None):
        return SimpleNamespace(
            id=uuid4(),
            source_video_id=uuid4(),
            status=status,
            score=score,
            score_version="REUP_SCORE_V1",
            score_label="usable",
            score_breakdown_json={"engagement_quality": {"raw_input": {"views": 0, "likes": 0, "comments": 0, "shares": 0}}},
            score_reason=None,
            preset_name=None,
            filter_config_json={},
            inclusion_reasons_json=[],
            exclusion_reasons_json=[],
            warnings_json=["missing view count"],
            evaluated_at=None,
            priority=55,
            metadata_json=metadata or {},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_video=source_video or self._source_video(),
        )

    def _capture_item(self, *, item_id=None, aweme_id="7420000000000000001", metadata=None, source_url=None, caption="Fixture"):
        item_id = item_id or uuid4()
        return SimpleNamespace(
            id=item_id,
            capture_session_id=uuid4(),
            capture_session=SimpleNamespace(id=uuid4(), submitted_profile_url="https://www.douyin.com/user/test"),
            source_video_external_id=aweme_id,
            source_url=source_url or f"https://www.douyin.com/video/{aweme_id}",
            share_url=None,
            profile_url="https://www.douyin.com/user/test",
            caption=caption,
            duration_seconds=61,
            posted_at=None,
            thumbnail_url="https://cdn.example.test/thumb.jpg",
            raw_payload_json={},
            metadata_json=metadata or {
                "reup_score": 66,
                "estimated_views_display": "6.6K-8.8K",
                "estimated_views_min": 6600,
                "estimated_views_max": 8800,
                "estimated_views_mid": 7700,
                "duration_text": "01:01",
                "posted_display": "27/03/2026",
                "like_count": 205,
                "comment_count": 21,
                "share_count": 13,
                "favorite_count": 2,
                "engagement_rate": 0.12,
                "has_estimated_views": True,
            },
            promoted_video_candidate_id=None,
            promoted_source_video_id=None,
        )

    def test_candidate_response_hydrates_canonical_fields_from_metadata_without_fake_zeroes(self) -> None:
        snapshot = {"capture_item_id": "capture-item-1", "source": "douyin", "source_module": "capture_inbox", "aweme_id": "7420000000000000001", "like_count": 0, "comment_count": None, "share_count": None, "posted_display": "23:00:00 24/3/2026", "posted_text_raw": "24/3/2026", "has_estimated_views": True, "reup_score": 42, "estimated_views_display": "1.2K", "estimated_views_mid": 1200, "thumbnail_url": "https://cdn.example.test/thumb.jpg", "source_metadata_version": "22F-1F"}
        candidate = self._candidate(
            metadata={"source_metadata": snapshot, "capture_item_id": "stale", "reup_score": 7},
            source_video=self._source_video(metadata={"estimated_views_display": "source-video-stale", "estimated_views_mid": 900, "reup_score": 87}),
        )

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(response.capture_item_id, "capture-item-1")
        self.assertEqual(response.estimated_views_display, "1.2K")
        self.assertEqual(response.like_count, 0)
        self.assertIsNone(response.comment_count)
        self.assertEqual(response.reup_score, 42)
        self.assertEqual(response.score, 55.0)
        self.assertEqual(response.source_metadata["source_metadata_version"], "22F-1F")
        self.assertEqual(response.review_board_trace_version, "22F-1H")
        self.assertEqual(response.review_candidate_debug["traceVersion"], "22F-1H")
        self.assertEqual(response.review_candidate_debug["scoreSource"], "source_metadata.reup_score")
        self.assertEqual(response.review_candidate_debug["scoreValue"], 42)
        self.assertEqual(response.review_candidate_debug["estimatedViewsSource"], "source_metadata.estimated_views_display")
        self.assertEqual(response.review_candidate_debug["metricsSource"], "source_metadata")

    def test_raccoon_posted_duration_contract_preserves_capture_snapshot_display(self) -> None:
        snapshot = {
            "caption": "114浣熊与黑熊 fixture",
            "posted_at": "2026-04-02T16:00:00Z",
            "posted_display": "23:00:00 2/4/2026",
            "posted_text_raw": "2/4/2026",
            "duration_seconds": 734,
            "duration_text": "12:14",
            "source_metadata_version": "22F-1H",
        }
        candidate = self._candidate(
            metadata={"source_metadata": snapshot},
            source_video=self._source_video(metadata={}, source_url="https://www.douyin.com/video/7621140000000000000"),
        )
        candidate.source_video.posted_at = datetime(2026, 4, 2, 16, 0, tzinfo=UTC)
        candidate.source_video.duration_seconds = 734

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(response.posted_display, "23:00:00 2/4/2026")
        self.assertEqual(response.postedDisplay, "23:00:00 2/4/2026")
        self.assertNotEqual(response.posted_display, "03/04/2026")
        self.assertEqual(response.duration_text, "12:14")
        self.assertEqual(response.durationText, "12:14")
        self.assertEqual(response.duration_seconds, 734)
        self.assertEqual(response.durationSeconds, 734)
        self.assertEqual(response.review_candidate_debug["postedDisplaySource"], "source_metadata.posted_display")
        self.assertEqual(response.review_candidate_debug["durationSource"], "source_metadata.duration_text")

    def test_bird_case_preserves_raw_capture_posted_display_over_posted_at(self) -> None:
        snapshot = {
            "caption": "190最聪明的鱼和最奇怪的鸟",
            "posted_at": "2026-04-02T16:00:00Z",
            "posted_display": "23:00:00 2/4/2026",
            "posted_text_raw": "2/4/2026",
            "duration_seconds": 734,
            "duration_text": "12:14",
            "reup_score": 42,
            "estimated_views_display": "3.8K-19K",
            "estimated_views_min": 3800,
            "estimated_views_mid": 11400,
            "estimated_views_max": 19000,
            "like_count": 190,
            "comment_count": 7,
            "share_count": 5,
            "source_metadata_version": "22F-1H-1",
        }
        candidate = self._candidate(
            metadata={"source_metadata": snapshot, "posted_display": "03/04/2026"},
            source_video=self._source_video(metadata={}, source_url="https://www.douyin.com/video/7621900000000000000"),
        )
        candidate.source_video.caption = "190最聪明的鱼和最奇怪的鸟"
        candidate.source_video.posted_at = datetime(2026, 4, 2, 16, 0, tzinfo=UTC)
        candidate.source_video.duration_seconds = 734

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(response.caption, "190最聪明的鱼和最奇怪的鸟")
        self.assertEqual(response.source_metadata["posted_display"], "23:00:00 2/4/2026")
        self.assertEqual(response.source_metadata["posted_text_raw"], "2/4/2026")
        self.assertEqual(response.posted_display, "23:00:00 2/4/2026")
        self.assertEqual(response.postedDisplay, "23:00:00 2/4/2026")
        self.assertNotEqual(response.posted_display, "03/04/2026")
        self.assertEqual(response.duration_text, "12:14")
        self.assertEqual(response.reup_score, 42)
        self.assertEqual(response.estimated_views_display, "3.8K-19K")
        self.assertEqual(response.like_count, 190)
        self.assertEqual(response.comment_count, 7)
        self.assertEqual(response.share_count, 5)
        self.assertEqual(response.review_candidate_debug["postedDisplaySource"], "source_metadata.posted_display")
        self.assertEqual(response.review_candidate_debug["postedDisplayValue"], "23:00:00 2/4/2026")
        self.assertEqual(response.review_candidate_debug["postedAtValue"], "2026-04-02T16:00:00Z")
        self.assertFalse(response.review_candidate_debug["postedDisplayWasFormatted"])

    def test_buffalo_yak_case_uses_exact_capture_inbox_posted_display_with_time(self) -> None:
        snapshot = {
            "caption": "103麝牛 无法抵抗的命运",
            "posted_at": "2026-05-03T02:40:00+00:00",
            "posted_display_exact": "09:40:00 3/5/2026",
            "posted_display": "09:40:00 3/5/2026",
            "posted_text_raw": "1周前",
            "duration_seconds": 637.047,
            "duration_text": "10:37",
            "reup_score": 43,
            "estimated_views_display": "2.1K-10.3K",
            "estimated_views_min": 2060,
            "estimated_views_mid": 3399,
            "estimated_views_max": 10300,
            "like_count": 103,
            "comment_count": 5,
            "share_count": 11,
            "source_metadata_version": "22F-1H-2",
        }
        candidate = self._candidate(
            metadata={"source_metadata": snapshot, "posted_display": "03/05/2026"},
            source_video=self._source_video(external_id="7634938045598289206", metadata={}),
        )
        candidate.source_video.posted_at = datetime(2026, 5, 3, 2, 40, tzinfo=UTC)

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(response.posted_display_exact, "09:40:00 3/5/2026")
        self.assertEqual(response.posted_display, "09:40:00 3/5/2026")
        self.assertEqual(response.postedDisplay, "09:40:00 3/5/2026")
        self.assertNotEqual(response.posted_display, "03/05/2026")
        self.assertEqual(response.reup_score, 43)
        self.assertEqual(response.estimated_views_display, "2.1K-10.3K")
        self.assertEqual(response.like_count, 103)
        self.assertEqual(response.comment_count, 5)
        self.assertEqual(response.share_count, 11)
        self.assertEqual(response.duration_text, "10:37")
        self.assertEqual(response.review_candidate_debug["postedDisplaySource"], "source_metadata.posted_display_exact")
        self.assertEqual(response.review_candidate_debug["postedDisplayExactValue"], "09:40:00 3/5/2026")
        self.assertFalse(response.review_candidate_debug["postedDisplayWasFormatted"])

    def test_capture_inbox_exact_posted_helper_matches_card_posted_at_source(self) -> None:
        item = self._capture_item(
            aweme_id="7634938045598289206",
            caption="103麝牛 无法抵抗的命运",
            metadata={"posted_display": "03/05/2026", "posted_text_raw": "1周前"},
        )
        item.posted_at = datetime(2026, 5, 3, 2, 40, tzinfo=UTC)

        result = getCaptureInboxPostedDisplayExact(item)

        self.assertEqual(result["value"], "09:40:00 3/5/2026")
        self.assertEqual(result["source"], "apps/web/src/lib/captureInboxCanonical.ts:resolvePosted->formatDateTime(item.posted_at)")

    def test_bird_hydration_refreshes_stale_posted_display_without_status_or_notes_changes(self) -> None:
        item = self._capture_item(
            aweme_id="7621900000000000000",
            caption="190最聪明的鱼和最奇怪的鸟",
            metadata={
                "caption": "190最聪明的鱼和最奇怪的鸟",
                "posted_at": "2026-04-02T16:00:00Z",
                "posted_display": "23:00:00 2/4/2026",
                "posted_text_raw": "2/4/2026",
                "duration_seconds": 734,
                "duration_text": "12:14",
                "reup_score": 42,
                "estimated_views_display": "3.8K-19K",
                "estimated_views_min": 3800,
                "estimated_views_mid": 11400,
                "estimated_views_max": 19000,
                "like_count": 190,
                "comment_count": 7,
                "share_count": 5,
            },
        )
        item.duration_seconds = 734
        item.posted_at = datetime(2026, 4, 2, 16, 0, tzinfo=UTC)
        candidate = self._candidate(
            status=CandidateStatus.REJECTED,
            metadata={
                "aweme_id": "7621900000000000000",
                "posted_display": "03/04/2026",
                "operator_notes": "keep this rejection note",
            },
        )

        result = CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(candidate)
        response = CandidateDetailResponse.model_validate(candidate)

        self.assertTrue(result["hydrated"])
        self.assertEqual(candidate.status, CandidateStatus.REJECTED)
        self.assertEqual(candidate.metadata_json["operator_notes"], "keep this rejection note")
        self.assertEqual(candidate.metadata_json["posted_display"], "23:00:00 2/4/2026")
        self.assertEqual(candidate.metadata_json["source_metadata"]["posted_display"], "23:00:00 2/4/2026")
        self.assertEqual(response.postedDisplay, "23:00:00 2/4/2026")
        self.assertFalse(response.review_candidate_debug["postedDisplayWasFormatted"])

    def test_hydration_fills_missing_card_metadata_by_capture_item_id_and_preserves_status(self) -> None:
        item = self._capture_item(caption="205海洋，生命的起源 fixture")
        candidate = self._candidate(metadata={"capture_item_id": str(item.id), "caption": "205海洋，生命的起源 fixture", "like_count": 205, "comment_count": 21, "share_count": 13})
        result = CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(candidate)

        self.assertTrue(result["hydrated"])
        self.assertEqual(candidate.status, CandidateStatus.SHORTLISTED)
        self.assertEqual(candidate.metadata_json["reup_score"], 32)
        self.assertEqual(candidate.metadata_json["estimated_views_display"], "6.6K-8.8K")
        self.assertEqual(candidate.metadata_json["duration_text"], "01:01")
        self.assertEqual(candidate.metadata_json["posted_display"], "27/03/2026")
        self.assertEqual(candidate.metadata_json["thumbnail_url"], "https://cdn.example.test/thumb.jpg")
        self.assertEqual(candidate.metadata_json["like_count"], 205)
        self.assertEqual(candidate.metadata_json["comment_count"], 21)
        self.assertEqual(candidate.metadata_json["share_count"], 13)
        self.assertEqual(candidate.metadata_json["review_board_hydration_debug"]["match_key"], "capture_item_id")

    def test_hydration_fills_missing_metadata_by_aweme_id_preserves_approved_rejected_and_zeroes(self) -> None:
        item = self._capture_item(metadata={"reup_score": 71, "estimated_views_display": "7.1K", "like_count": None, "comment_count": 0, "share_count": 13})
        approved = self._candidate(status=CandidateStatus.APPROVED, metadata={"aweme_id": "7420000000000000001", "like_count": 0})
        rejected = self._candidate(status=CandidateStatus.REJECTED, metadata={"aweme_id": "7420000000000000001", "operator_notes": "keep my note"})

        CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(approved)
        CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(rejected)

        self.assertEqual(approved.status, CandidateStatus.APPROVED)
        self.assertEqual(approved.metadata_json["like_count"], 0)
        self.assertEqual(approved.metadata_json["comment_count"], 0)
        self.assertEqual(approved.metadata_json["reup_score"], 12)
        self.assertEqual(rejected.status, CandidateStatus.REJECTED)
        self.assertEqual(rejected.metadata_json["operator_notes"], "keep my note")
        self.assertEqual(rejected.metadata_json["review_board_hydration_debug"]["match_key"], "aweme_id")

    def test_hydration_does_not_fake_missing_estimated_views_and_reports_summary_debug(self) -> None:
        item = self._capture_item(metadata={"reup_score": 31, "like_count": 1, "comment_count": 2, "share_count": 3})
        candidate = self._candidate(metadata={"aweme_id": "7420000000000000001"})
        service = CandidateEvaluationService(FakeHydrationDb(item))
        service.hydrateReviewCandidateFromCaptureItem(candidate)
        response = CandidateDetailResponse.model_validate(candidate)
        summary = service.hydration_summary([candidate])
        payload = CandidateListResponse(
            view="detail",
            total_count=1,
            offset=0,
            limit=50,
            candidates=[response],
            review_board_hydration_summary=summary,
        )

        self.assertIsNone(candidate.metadata_json.get("estimated_views_display"))
        self.assertEqual(summary["candidates_missing_estimated_views"], 1)
        self.assertEqual(payload.review_board_hydration_summary["total_candidates"], 1)
        self.assertTrue(response.review_candidate_debug["hydrationAttempted"])
        self.assertEqual(response.review_candidate_debug["hydrationMatchKey"], "aweme_id")

    def test_phase22f_1g_normal_and_debug_api_contract_match_for_fish_sample(self) -> None:
        snapshot = {
            "capture_item_id": "fish-capture-id",
            "source": "douyin",
            "source_module": "capture_inbox",
            "aweme_id": "7622664109737250084",
            "caption": "183珊瑚礁拥有自己的生态链 fixture",
            "source_url": "https://www.douyin.com/video/7622664109737250084",
            "profile_url": "https://www.douyin.com/user/fish",
            "thumbnail_url": "https://cdn.example.test/fish.jpg",
            "posted_at": "2026-03-28T16:00:00Z",
            "posted_display": "23:00:00 28/3/2026",
            "duration_seconds": 816.88,
            "duration_text": "13:37",
            "reup_score": 42,
            "estimated_views_display": "3.7K-18.3K",
            "estimated_views_min": 3660,
            "estimated_views_mid": 6039,
            "estimated_views_max": 18300,
            "like_count": 183,
            "comment_count": 12,
            "share_count": 13,
            "review_status": "SHORTLISTED",
            "decision_status": "needs_review",
            "source_metadata_version": "22F-1G",
        }
        candidate = self._candidate(
            metadata={"source_metadata": snapshot, "operator_notes": "preserve note"},
            score=21.05,
            source_video=self._source_video(external_id="7622664109737250084", source_url=snapshot["source_url"], metadata={}),
        )

        response = CandidateDetailResponse.model_validate(candidate)
        payload = CandidateListResponse(
            view="detail",
            total_count=1,
            offset=0,
            limit=50,
            candidates=[response],
            review_board_hydration_summary={"total_candidates": 1},
        )
        serialized = payload.model_dump(mode="json")["candidates"][0]
        debug = serialized["review_candidate_debug"]

        self.assertEqual(serialized["reup_score"], 42)
        self.assertEqual(serialized["score"], 21.05)
        self.assertEqual(debug["visibleScore"], serialized["reup_score"])
        self.assertEqual(debug["scoreSource"], "source_metadata.reup_score")
        self.assertEqual(serialized["estimated_views_display"], "3.7K-18.3K")
        self.assertEqual(debug["estimatedViewsDisplay"], serialized["estimated_views_display"])
        self.assertEqual(serialized["estimated_views_min"], 3660)
        self.assertEqual(serialized["estimated_views_max"], 18300)
        self.assertEqual(serialized["like_count"], 183)
        self.assertEqual(serialized["comment_count"], 12)
        self.assertEqual(serialized["share_count"], 13)
        self.assertEqual(serialized["duration_text"], "13:37")
        self.assertEqual(serialized["posted_display"], "23:00:00 28/3/2026")
        self.assertEqual(serialized["thumbnail_url"], "https://cdn.example.test/fish.jpg")
        self.assertEqual(serialized["aweme_id"], "7622664109737250084")
        self.assertEqual(serialized["capture_item_id"], "fish-capture-id")
        self.assertEqual(serialized["review_status"], "SHORTLISTED")
        self.assertEqual(serialized["decision_status"], "needs_review")
        self.assertEqual(response.metadata_json["operator_notes"], "preserve note")

    def test_phase22f_1g_legacy_nested_metadata_normalizes_without_internal_score(self) -> None:
        source_video = self._source_video(
            external_id="legacy-aweme",
            metadata={
                "source_metadata": {
                    "reup_score": 42,
                    "estimated_views_display": "3.7K-18.3K",
                    "estimated_views_min": 3660,
                    "estimated_views_max": 18300,
                    "duration_text": "13:37",
                    "posted_display": "23:00:00 28/3/2026",
                    "like_count": 183,
                    "comment_count": 12,
                    "share_count": 13,
                }
            },
        )
        candidate = self._candidate(metadata={"operator_notes": "legacy note"}, score=21.05, source_video=source_video)

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(response.reup_score, 42)
        self.assertEqual(response.score, 21.05)
        self.assertEqual(response.review_candidate_debug["scoreSource"], "source_metadata.reup_score")
        self.assertEqual(response.estimated_views_display, "3.7K-18.3K")
        self.assertEqual(response.estimated_views_min, 3660)
        self.assertEqual(response.estimated_views_max, 18300)
        self.assertEqual(response.duration_text, "13:37")
        self.assertEqual(response.posted_display, "23:00:00 28/3/2026")
        self.assertEqual(response.like_count, 183)
        self.assertEqual(response.comment_count, 12)
        self.assertEqual(response.share_count, 13)
        self.assertEqual(response.metadata_json["operator_notes"], "legacy note")

    def test_phase22f_1g_truly_missing_metadata_stays_null_not_zero(self) -> None:
        candidate = self._candidate(metadata={}, score=21.05, source_video=self._source_video(metadata={}))

        response = CandidateDetailResponse.model_validate(candidate)

        self.assertIsNone(response.reup_score)
        self.assertEqual(response.score, 21.05)
        self.assertEqual(response.review_candidate_debug["scoreSource"], "missing")
        self.assertIsNone(response.estimated_views_display)
        self.assertIsNone(response.estimated_views_min)
        self.assertIsNone(response.estimated_views_max)
        self.assertIsNone(response.estimated_views_mid)
        self.assertIsNone(response.like_count)
        self.assertIsNone(response.comment_count)
        self.assertIsNone(response.share_count)
        self.assertEqual(response.review_candidate_debug["estimatedViewsSource"], "missing")
        self.assertEqual(response.review_candidate_debug["metricsSource"], "missing")

    def test_fish_capture_shape_derives_review_board_score_and_estimated_views(self) -> None:
        item = self._capture_item(
            aweme_id="7622664109737250084",
            caption="183珊瑚礁拥有自己的生态链 fixture",
            metadata={
                "metadata_status": "complete",
                "performance_status": "captured",
                "like_count": 183,
                "comment_count": 12,
                "share_count": 13,
                "favorite_count": 41,
                "engagement_score": 249,
                "posted_at": "2026-03-28T16:00:00Z",
                "posted_display": "29/03/2026",
                "duration_seconds": 816.88,
                "duration_text": "13:37",
            },
        )
        item.duration_seconds = 816.88
        item.posted_at = datetime(2026, 3, 28, 16, 0, tzinfo=UTC)
        candidate = self._candidate(metadata={"capture_item_id": str(item.id), "aweme_id": "7622664109737250084", "reup_score": 49})

        result = CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(candidate)

        self.assertTrue(result["hydrated"])
        self.assertEqual(candidate.metadata_json["source_metadata"]["source_metadata_version"], "22F-1H-2")
        self.assertEqual(candidate.metadata_json["source_metadata"]["snapshot_source"], "live_db_backfill_22F_1H_2")
        self.assertEqual(candidate.metadata_json["source_metadata"]["reup_score"], 45)
        self.assertEqual(candidate.metadata_json["reup_score"], 45)
        self.assertEqual(candidate.metadata_json["estimated_views_display"], "3.7K-18.3K")
        self.assertEqual(candidate.metadata_json["estimated_views_min"], 3660)
        self.assertEqual(candidate.metadata_json["estimated_views_mid"], 6039)
        self.assertEqual(candidate.metadata_json["estimated_views_max"], 18300)
        self.assertEqual(candidate.metadata_json["like_count"], 183)
        self.assertEqual(candidate.metadata_json["comment_count"], 12)
        self.assertEqual(candidate.metadata_json["share_count"], 13)
        comparison = candidate.metadata_json["capture_to_review_comparison"]
        self.assertEqual(comparison["traceVersion"], "22F-1F")
        self.assertTrue(comparison["fields"]["reup_score"]["match"])
        self.assertTrue(comparison["fields"]["estimated_views_display"]["match"])

    def test_phase22f_1g_backfill_preserves_decision_notes_and_missing_values(self) -> None:
        item = self._capture_item(metadata={"reup_score": 31, "like_count": 1, "comment_count": 2, "share_count": 3})
        candidate = self._candidate(
            status=CandidateStatus.APPROVED,
            metadata={"aweme_id": "7420000000000000001", "decision_status": "approved", "operator_notes": "do not overwrite"},
        )

        CandidateEvaluationService(FakeHydrationDb(item)).hydrateReviewCandidateFromCaptureItem(candidate)
        response = CandidateDetailResponse.model_validate(candidate)

        self.assertEqual(candidate.status, CandidateStatus.APPROVED)
        self.assertEqual(candidate.metadata_json["decision_status"], "approved")
        self.assertEqual(candidate.metadata_json["operator_notes"], "do not overwrite")
        self.assertEqual(response.reup_score, 7)
        self.assertIsNone(response.estimated_views_display)
        self.assertIsNone(response.estimated_views_min)
        self.assertIsNone(response.estimated_views_max)
        self.assertIsNone(response.estimated_views_mid)
        self.assertEqual(response.like_count, 1)
        self.assertEqual(response.comment_count, 2)
        self.assertEqual(response.share_count, 3)

    def test_hydration_reports_not_hydratable_without_duplicate_candidate(self) -> None:
        candidate = self._candidate(metadata={"caption": "unmatched"})
        service = CandidateEvaluationService(FakeHydrationDb(None))
        result = service.hydrateReviewCandidateFromCaptureItem(candidate)
        summary = service.hydration_summary([candidate])

        self.assertFalse(result["hydrated"])
        self.assertEqual(summary["candidates_not_hydratable"], 1)
        self.assertEqual(summary["not_hydratable_reasons"]["no_capture_item_match"], 1)
        self.assertEqual(candidate.id, candidate.id)

    def test_promote_raw_detail_reports_updated_existing_metadata_trace(self) -> None:
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7621110952095665451",
            promoted_video_candidate_id=uuid4(),
            duration_seconds=1033,
            metadata_json={"review_board_duplicate_detected": True, "metadata_snapshot_created": True, "source_metadata": {"source_metadata_version": "22F-1F", "reup_score": 42, "estimated_views_display": "4.1K-20.3K", "like_count": 203, "comment_count": 7, "share_count": 18, "posted_display": "23:00:00 24/3/2026"}},
        )

        detail = _promotion_raw_detail(item)

        self.assertEqual(detail["aweme_id"], "7621110952095665451")
        self.assertEqual(detail["action"], "updated_existing")
        self.assertEqual(detail["metadata_updated"], True)
        self.assertEqual(detail["reup_score"], 42)
        self.assertEqual(detail["estimated_views_display"], "4.1K-20.3K")
        self.assertEqual(detail["metadata_snapshot_created"], True)
        self.assertEqual(detail["source_metadata_version"], "22F-1F")
        self.assertEqual(detail["traceVersion"], "22F-1F")


if __name__ == "__main__":
    unittest.main()
