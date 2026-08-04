"""Every finished clip leaves a pile of intermediates behind.

Stems, extracted audio, per-line TTS clips and OCR frames exist only to produce the final
render. Nothing deletes them today, so a few hundred clips quietly fill the volume and the
disk guard starts refusing work on a drive full of garbage. Reclaiming them is only safe
under strict conditions: the clip must be finished, the final render must exist, and the
files must be old enough that an operator reviewing today still has them.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import MediaAssetStatus, MediaAssetType, ReupQueueStatus
from src.services.artifact_retention import (
    PROTECTED_ASSET_TYPES,
    RECLAIMABLE_ASSET_TYPES,
    is_reclaimable_asset,
    item_is_finished,
    plan_reclaim,
    reclaim_min_age,
    retention_enabled,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def asset(
    asset_type: MediaAssetType,
    *,
    age_hours: float = 48,
    size_bytes: int = 100_000_000,
    status: MediaAssetStatus = MediaAssetStatus.AVAILABLE,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        asset_type=asset_type,
        status=status,
        storage_key="ws/dy/@u__abc/audio/x.wav",
        logical_key="ws/dy/@u__abc/audio/x.wav",
        size_bytes=size_bytes,
        created_at=NOW - timedelta(hours=age_hours),
        is_current=True,
    )


class AssetClassTests(unittest.TestCase):
    def test_the_source_and_the_deliverable_are_never_touched(self) -> None:
        for kept in (
            MediaAssetType.SOURCE_VIDEO_RAW,
            MediaAssetType.FINAL_RENDER_VIDEO,
            MediaAssetType.RENDER_OUTPUT,
            MediaAssetType.THUMBNAIL,
        ):
            self.assertIn(kept, PROTECTED_ASSET_TYPES)
            self.assertNotIn(kept, RECLAIMABLE_ASSET_TYPES)

    def test_regenerable_intermediates_are_reclaimable(self) -> None:
        for reclaimable in (
            MediaAssetType.AUDIO_VOCAL_STEM,
            MediaAssetType.AUDIO_BACKGROUND_STEM,
            MediaAssetType.SOURCE_AUDIO_EXTRACT,
            MediaAssetType.TTS_AUDIO_CLIP,
            MediaAssetType.OCR_FRAME,
            MediaAssetType.TEMP_FILE,
        ):
            self.assertIn(reclaimable, RECLAIMABLE_ASSET_TYPES)

    def test_transcripts_and_subtitles_stay_because_they_are_small_and_edited(self) -> None:
        for kept in (
            MediaAssetType.TRANSCRIPT_JSON,
            MediaAssetType.TRANSLATION_DRAFT_JSON,
            MediaAssetType.SUBTITLE_ASS,
        ):
            self.assertNotIn(kept, RECLAIMABLE_ASSET_TYPES)

    def test_the_cleaned_video_needs_an_explicit_opt_in(self) -> None:
        cleaned = asset(MediaAssetType.CLEANED_VIDEO)

        self.assertFalse(is_reclaimable_asset(cleaned, now=NOW, min_age=timedelta(hours=24)))
        self.assertTrue(
            is_reclaimable_asset(cleaned, now=NOW, min_age=timedelta(hours=24), include_cleaned_video=True),
            "Operators who re-render from the cleaned video can keep it; others reclaim the space",
        )


class AgeAndStateTests(unittest.TestCase):
    def test_a_fresh_intermediate_is_left_alone(self) -> None:
        self.assertFalse(
            is_reclaimable_asset(asset(MediaAssetType.AUDIO_VOCAL_STEM, age_hours=2), now=NOW, min_age=timedelta(hours=24)),
            "Someone may still be reviewing this clip",
        )

    def test_an_old_intermediate_is_reclaimable(self) -> None:
        self.assertTrue(
            is_reclaimable_asset(asset(MediaAssetType.AUDIO_VOCAL_STEM), now=NOW, min_age=timedelta(hours=24))
        )

    def test_an_already_archived_asset_is_skipped(self) -> None:
        self.assertFalse(
            is_reclaimable_asset(
                asset(MediaAssetType.AUDIO_VOCAL_STEM, status=MediaAssetStatus.ARCHIVED),
                now=NOW,
                min_age=timedelta(hours=24),
            ),
            "Reclaiming twice would delete nothing and log noise",
        )


class FinishedItemTests(unittest.TestCase):
    def test_a_completed_item_is_finished(self) -> None:
        self.assertTrue(item_is_finished(SimpleNamespace(status=ReupQueueStatus.COMPLETED, metadata_json={})))

    def test_an_item_still_moving_is_not_finished(self) -> None:
        self.assertFalse(
            item_is_finished(
                SimpleNamespace(
                    status=ReupQueueStatus.PROCESSING,
                    metadata_json={"pipeline_mode": "auto_to_render", "pipeline_step": "render"},
                )
            )
        )

    def test_an_item_stranded_for_attention_keeps_its_evidence(self) -> None:
        self.assertFalse(
            item_is_finished(
                SimpleNamespace(
                    status=ReupQueueStatus.FAILED_NEEDS_ATTENTION,
                    metadata_json={"pipeline_step": "needs_attention"},
                )
            ),
            "Debugging a failure needs the intermediates that produced it",
        )

    def test_a_render_that_failed_qa_keeps_its_evidence(self) -> None:
        self.assertFalse(
            item_is_finished(
                SimpleNamespace(
                    status=ReupQueueStatus.READY_TO_EXPORT,
                    metadata_json={"pipeline_step": "ready_final", "render_qa": {"status": "fail"}},
                )
            )
        )

    def test_a_render_with_only_warnings_can_be_reclaimed(self) -> None:
        self.assertTrue(
            item_is_finished(
                SimpleNamespace(
                    status=ReupQueueStatus.READY_TO_EXPORT,
                    metadata_json={"pipeline_step": "ready_final", "render_qa": {"status": "warn"}},
                )
            )
        )


class PlanTests(unittest.TestCase):
    def test_plan_keeps_protected_assets_and_returns_the_rest(self) -> None:
        assets = [
            asset(MediaAssetType.SOURCE_VIDEO_RAW),
            asset(MediaAssetType.FINAL_RENDER_VIDEO),
            asset(MediaAssetType.AUDIO_VOCAL_STEM),
            asset(MediaAssetType.OCR_FRAME, size_bytes=2_000_000),
        ]

        plan = plan_reclaim(assets, now=NOW, min_age=timedelta(hours=24))

        self.assertEqual({entry.asset_type for entry in plan.assets}, {MediaAssetType.AUDIO_VOCAL_STEM, MediaAssetType.OCR_FRAME})
        self.assertEqual(plan.bytes_reclaimable, 102_000_000)

    def test_nothing_is_planned_without_a_final_render(self) -> None:
        plan = plan_reclaim(
            [asset(MediaAssetType.AUDIO_VOCAL_STEM), asset(MediaAssetType.SOURCE_VIDEO_RAW)],
            now=NOW,
            min_age=timedelta(hours=24),
        )

        self.assertEqual(plan.assets, [], "Without a deliverable the intermediates are all we have")

    def test_a_render_output_also_counts_as_the_deliverable(self) -> None:
        plan = plan_reclaim(
            [asset(MediaAssetType.RENDER_OUTPUT), asset(MediaAssetType.AUDIO_VOCAL_STEM)],
            now=NOW,
            min_age=timedelta(hours=24),
        )

        self.assertEqual(len(plan.assets), 1)

    def test_missing_sizes_do_not_break_the_estimate(self) -> None:
        stem = asset(MediaAssetType.AUDIO_VOCAL_STEM)
        stem.size_bytes = None

        plan = plan_reclaim([asset(MediaAssetType.FINAL_RENDER_VIDEO), stem], now=NOW, min_age=timedelta(hours=24))

        self.assertEqual(plan.bytes_reclaimable, 0)
        self.assertEqual(len(plan.assets), 1)


class SettingsTests(unittest.TestCase):
    def test_retention_is_opt_in_per_deployment(self) -> None:
        self.assertTrue(retention_enabled(SimpleNamespace(artifact_retention_enabled=True)))
        self.assertFalse(retention_enabled(SimpleNamespace(artifact_retention_enabled=False)))

    def test_minimum_age_comes_from_settings_with_a_floor(self) -> None:
        self.assertEqual(reclaim_min_age(SimpleNamespace(artifact_retention_min_age_hours=48)), timedelta(hours=48))
        self.assertGreaterEqual(
            reclaim_min_age(SimpleNamespace(artifact_retention_min_age_hours=0)),
            timedelta(hours=1),
            "An immediate sweep would delete files an operator is still looking at",
        )


class SweepTests(unittest.TestCase):
    def _sweep(self, assets: list[SimpleNamespace], storage: MagicMock, *, item_status=ReupQueueStatus.COMPLETED):
        from src.services.artifact_retention import reclaim_item_artifacts

        item = SimpleNamespace(
            id=uuid4(),
            status=item_status,
            source_video_id=uuid4(),
            metadata_json={"pipeline_step": "ready_final"},
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = assets
        return reclaim_item_artifacts(db, item, storage=storage, now=NOW, min_age=timedelta(hours=24))

    def test_files_are_deleted_and_rows_archived(self) -> None:
        stem = asset(MediaAssetType.AUDIO_VOCAL_STEM)
        storage = MagicMock()

        result = self._sweep([asset(MediaAssetType.FINAL_RENDER_VIDEO), stem], storage)

        storage.delete.assert_called_once_with(stem.logical_key)
        self.assertEqual(stem.status, MediaAssetStatus.ARCHIVED)
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.bytes_reclaimed, 100_000_000)

    def test_an_unfinished_item_is_skipped_entirely(self) -> None:
        storage = MagicMock()

        result = self._sweep(
            [asset(MediaAssetType.FINAL_RENDER_VIDEO), asset(MediaAssetType.AUDIO_VOCAL_STEM)],
            storage,
            item_status=ReupQueueStatus.PROCESSING,
        )

        storage.delete.assert_not_called()
        self.assertEqual(result.deleted_count, 0)

    def test_a_missing_file_still_archives_the_row(self) -> None:
        stem = asset(MediaAssetType.AUDIO_VOCAL_STEM)
        storage = MagicMock()
        storage.delete.side_effect = FileNotFoundError("already gone")

        result = self._sweep([asset(MediaAssetType.FINAL_RENDER_VIDEO), stem], storage)

        self.assertEqual(stem.status, MediaAssetStatus.ARCHIVED, "A vanished file is the desired end state")
        self.assertEqual(result.deleted_count, 1)

    def test_a_storage_error_leaves_the_row_alone_for_the_next_pass(self) -> None:
        stem = asset(MediaAssetType.AUDIO_VOCAL_STEM)
        storage = MagicMock()
        storage.delete.side_effect = PermissionError("file in use")

        result = self._sweep([asset(MediaAssetType.FINAL_RENDER_VIDEO), stem], storage)

        self.assertEqual(stem.status, MediaAssetStatus.AVAILABLE)
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(result.failed_count, 1)


class DisabledSweepTests(unittest.TestCase):
    def test_the_sweep_does_nothing_while_disabled(self) -> None:
        from src.services.artifact_retention import sweep_reclaimable_artifacts

        db = MagicMock()
        with patch(
            "src.services.artifact_retention.get_settings",
            return_value=SimpleNamespace(artifact_retention_enabled=False),
        ):
            self.assertEqual(sweep_reclaimable_artifacts(db), 0)

        db.scalars.assert_not_called()


if __name__ == "__main__":
    unittest.main()
