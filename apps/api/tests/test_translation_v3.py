from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.providers import PlaceholderVietnameseTranslationProvider
from src.audio_pipeline.errors import AudioAnalysisError
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.speech_budget import extract_protected_tokens
from src.audio_pipeline.semantic_dialogue_segmentation import SEMANTIC_DIALOGUE_RECIPE_VERSION
from src.audio_pipeline.translation_temporal_premerge import plan_translation_premerge
from src.audio_pipeline.translation_llm import DurationConstrainedTranslationProvider, FixedLlmClient
from src.audio_pipeline.translation_v3 import (
    TRANSLATION_V3_RECIPE_VERSION,
    TranslationCandidate,
    TranslationV3Policy,
    adaptive_candidate_count,
    build_context_blocks,
    build_translation_quality_contract,
    draft_to_checkpoint,
    select_translation_candidate,
    translation_run_fingerprint,
)
from src.audio_pipeline.types import (
    TranscriptDraftSegment,
    TranslationDraftSegment,
    TranslationPreset,
)
from src.enums import JobStatus, JobType, TranscriptSegmentStatus
from src.models.artifacts import TranscriptSegment


def _beat(index: int, *, duration: float = 2.0, speaker: str | None = "speaker_1") -> TranscriptDraftSegment:
    return TranscriptDraftSegment(
        segment_index=index,
        start_seconds=index * duration,
        end_seconds=(index + 1) * duration,
        source_text=f"中文句子{index}",
        normalized_source_text=f"中文句子{index}",
        confidence=0.95,
        speaker_label=speaker,
        difficulty_flags=[],
        metadata={},
    )


def test_adaptive_candidate_count_spends_more_on_risky_segments() -> None:
    clean = _beat(0, duration=4.0)
    risky = TranscriptDraftSegment(
        segment_index=1,
        start_seconds=0.0,
        end_seconds=1.2,
        source_text="价格100元",
        normalized_source_text="价格100元",
        confidence=0.65,
        speaker_label=None,
        difficulty_flags=["needs_operator_review"],
        metadata={},
    )
    policy = TranslationV3Policy(candidate_count=3)
    assert adaptive_candidate_count(clean, policy=policy) == 1
    assert adaptive_candidate_count(risky, policy=policy) == 3


@dataclass
class _BlockProvider:
    calls: int = 0

    def translate_context_batch(self, block, *, preset, policy):
        del policy
        self.calls += 1
        return [
            TranslationDraftSegment(
                segment_index=int(row["segment_index"]),
                translated_text=f"Bản dịch ổn định cho câu {row['segment_index']}",
                translation_preset=preset,
                duration_budget_seconds=float(row["duration_seconds"]),
                estimated_tts_duration_seconds=float(row["duration_seconds"]),
                quality_flags=[],
                metadata={"provider": "block_test"},
            )
            for row in block["segments"]
        ]


class TranslationV3Tests(unittest.TestCase):
    def test_translation_job_rejects_failed_semantic_authority_contract(self) -> None:
        source_id = uuid4()
        workspace_id = uuid4()
        source = SimpleNamespace(
            id=source_id,
            workspace_id=workspace_id,
            metadata_json={
                "semantic_dialogue_segmentation": {
                    "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
                    "translation_ready": False,
                    "authority_preserved": False,
                }
            },
        )
        beat = SimpleNamespace(status=TranscriptSegmentStatus.APPROVED)
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
        )

        with patch.object(service, "_load_source_video", return_value=source), patch.object(
            service, "get_transcript_segments", return_value=[beat]
        ), self.assertRaises(AudioAnalysisError):
            service.create_translation_job(source_id)

    def test_premerge_attaches_terminal_micro_beat_to_previous_phrase(self) -> None:
        beats = [
            SimpleNamespace(
                id=uuid4(), segment_index=0, start_ms=0, end_ms=2_000,
                text="喜欢的话点个", normalized_text="喜欢的话点个",
                speaker_label="speaker_1", metadata_json={},
            ),
            SimpleNamespace(
                id=uuid4(), segment_index=1, start_ms=2_040, end_ms=2_330,
                text="关注吧", normalized_text="关注吧",
                speaker_label="speaker_1", metadata_json={},
            ),
        ]

        groups = plan_translation_premerge(beats)

        self.assertEqual(len(groups), 1)
        self.assertEqual([row.segment_index for row in groups[0].members], [0, 1])
        self.assertIn("micro_beat", groups[0].reasons)

    def test_premerge_attaches_short_incomplete_clause_to_following_phrase(self) -> None:
        beats = [
            SimpleNamespace(
                id=uuid4(), segment_index=4, start_ms=1_000, end_ms=2_420,
                text="沙漠银耳的特点是", normalized_text="沙漠银耳的特点是",
                speaker_label="speaker_1", metadata_json={},
            ),
            SimpleNamespace(
                id=uuid4(), segment_index=5, start_ms=2_500, end_ms=4_600,
                text="口感很脆", normalized_text="口感很脆",
                speaker_label="speaker_1", metadata_json={},
            ),
        ]

        groups = plan_translation_premerge(beats)

        self.assertEqual(len(groups), 1)
        self.assertIn("short_incomplete_clause", groups[0].reasons)

    def test_premerge_does_not_cross_speaker_or_large_gap(self) -> None:
        beats = [
            SimpleNamespace(
                id=uuid4(), segment_index=0, start_ms=0, end_ms=300,
                text="你好", normalized_text="你好", speaker_label="speaker_1", metadata_json={},
            ),
            SimpleNamespace(
                id=uuid4(), segment_index=1, start_ms=320, end_ms=650,
                text="您好", normalized_text="您好", speaker_label="speaker_2", metadata_json={},
            ),
            SimpleNamespace(
                id=uuid4(), segment_index=2, start_ms=2_000, end_ms=2_300,
                text="再见", normalized_text="再见", speaker_label="speaker_2", metadata_json={},
            ),
        ]

        groups = plan_translation_premerge(beats)

        self.assertEqual(len(groups), 3)

    def test_premerge_does_not_mutate_semantic_utterance_authority(self) -> None:
        semantic = SimpleNamespace(
            id=uuid4(), segment_index=0, start_ms=0, end_ms=500,
            text="好呀", normalized_text="好呀", speaker_label="speaker_1",
            metadata_json={
                "raw_payload": {
                    "semantic_segmentation": {
                        "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
                    }
                }
            },
        )
        neighbor = SimpleNamespace(
            id=uuid4(), segment_index=1, start_ms=520, end_ms=1_500,
            text="下一句完整内容", normalized_text="下一句完整内容",
            speaker_label="speaker_1", metadata_json={},
        )

        self.assertEqual(len(plan_translation_premerge([semantic, neighbor])), 2)

    def test_premerge_persists_new_transcript_version_without_overwriting_members(self) -> None:
        source_id = uuid4()
        workspace_id = uuid4()
        job_id = uuid4()
        left = TranscriptSegment(
            id=uuid4(), workspace_id=workspace_id, source_video_id=source_id,
            segment_index=7, version=4, start_ms=0, end_ms=1_800,
            text="喜欢的话点个", normalized_text="喜欢的话点个", language_code="zh",
            status=TranscriptSegmentStatus.APPROVED, confidence=0.97,
            speaker_label="speaker_1", difficulty_flags_json={"flags": ["source_flag"]},
            analysis_version="AUDIO_ANALYSIS_V2_RUN_4", is_current=True, metadata_json={},
        )
        right = TranscriptSegment(
            id=uuid4(), workspace_id=workspace_id, source_video_id=source_id,
            segment_index=8, version=4, start_ms=1_820, end_ms=2_110,
            text="关注吧", normalized_text="关注吧", language_code="zh",
            status=TranscriptSegmentStatus.APPROVED, confidence=0.91,
            speaker_label="speaker_1", difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V2_RUN_4", is_current=True, metadata_json={},
        )
        db = MagicMock()
        db.scalar.return_value = 4
        service = AudioAnalysisService(
            db=db,
            storage=MagicMock(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
        )
        source = SimpleNamespace(id=source_id, workspace_id=workspace_id, metadata_json={})

        def refreshed(_source_id):
            return [db.add.call_args.args[0]]

        with patch.object(service, "get_transcript_segments", side_effect=refreshed):
            rows, summary = service._materialize_translation_premerge(
                source, [left, right], job_id=job_id
            )

        merged = rows[0]
        self.assertFalse(left.is_current)
        self.assertFalse(right.is_current)
        self.assertEqual(left.text, "喜欢的话点个")
        self.assertEqual(right.text, "关注吧")
        self.assertEqual(merged.version, 5)
        self.assertEqual(merged.segment_index, 7)
        self.assertEqual(merged.text, "喜欢的话点个关注吧")
        self.assertEqual(merged.status, TranscriptSegmentStatus.APPROVED)
        self.assertEqual(merged.confidence, 0.91)
        self.assertEqual(merged.created_by_job_id, job_id)
        self.assertTrue(summary["materialized"])
        self.assertEqual(len(summary["lineage_sha256"]), 1)
        db.commit.assert_called_once()

        # Even when the merged duration is still microscopic, lineage locks it
        # against a second merge during a worker retry.
        merged.end_ms = 500
        neighbor = SimpleNamespace(
            id=uuid4(), segment_index=9, start_ms=520, end_ms=800,
            text="下一句", normalized_text="下一句", speaker_label="speaker_1", metadata_json={},
        )
        self.assertEqual(len(plan_translation_premerge([merged, neighbor])), 2)

    def test_gram_unit_requires_adjacent_ascii_number(self) -> None:
        self.assertEqual(extract_protected_tokens("100 g 花生油"), ("100", "g"))
        self.assertNotIn("g", tuple(token.casefold() for token in extract_protected_tokens("g 十 二")))
        self.assertNotIn("g", tuple(token.casefold() for token in extract_protected_tokens("G12 G7X3")))

    def test_camera_model_candidate_does_not_fall_back_as_gram_mismatch(self) -> None:
        client = FixedLlmClient(
            responses=[
                '[{"segment_id":"0","candidates":['
                '{"style":"faithful","text":"G12 là mẫu máy ảnh rất ổn định."},'
                '{"style":"natural","text":"G12 là chiếc máy ảnh rất ổn."},'
                '{"style":"compact","text":"Máy G12 rất ổn."}'
                ']}]'
            ]
        )
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            allow_machine_translate_recovery=False,
            max_rewrite_rounds=0,
        )
        beat = TranscriptDraftSegment(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=3.0,
            source_text="g 十 二 是 一 台 很 稳 定 的 相 机",
            normalized_source_text="g 十 二 是 一 台 很 稳 定 的 相 机",
            confidence=0.95,
            speaker_label="speaker_1",
            difficulty_flags=[],
            metadata={},
        )

        row = TranslationDraftBuilder(provider).build(
            [beat], preset=TranslationPreset.LITERAL_SAFE
        )[0]

        self.assertEqual(row.metadata["translation_v3"]["status"], "candidate_selected")
        self.assertNotIn("protected_token_mismatch", row.quality_flags)

    def test_context_blocks_keep_authority_rows_unique_and_neighbors_read_only(self) -> None:
        beats = [_beat(index) for index in range(7)]
        policy = TranslationV3Policy(max_core_beats=3, max_block_seconds=30.0, context_overlap_beats=2)

        blocks = build_context_blocks(beats, policy=policy)

        self.assertEqual([[row.segment_index for row in block.core_segments] for block in blocks], [[0, 1, 2], [3, 4, 5], [6]])
        self.assertEqual([row.segment_index for row in blocks[1].context_before], [1, 2])
        self.assertEqual([row.segment_index for row in blocks[1].context_after], [6])
        authority = [row.segment_index for block in blocks for row in block.core_segments]
        self.assertEqual(authority, list(range(7)))

    def test_candidate_ranker_rejects_missing_protected_facts(self) -> None:
        selection = select_translation_candidate(
            "加入 100 g 花生油",
            [
                TranslationCandidate("Thêm dầu lạc vào.", style="faithful"),
                TranslationCandidate("Cho đúng 100 g dầu lạc vào nhé.", style="natural"),
                TranslationCandidate("Cho 100 g dầu lạc vào.", style="compact"),
            ],
            slot_seconds=1.8,
        )

        self.assertIsNotNone(selection.selected)
        self.assertIn("100", selection.selected.text)
        self.assertIn("g", selection.selected.text)
        self.assertFalse(selection.evaluations[0]["hard_valid"])
        self.assertIn("protected_token_mismatch", selection.evaluations[0]["issues"])

    def test_candidate_ranker_prefers_acceptable_timing_band_before_small_score_gain(self) -> None:
        selection = select_translation_candidate(
            "无污染空气洁净的环境",
            [
                TranslationCandidate("môi trường sạch, không khí cũng rất trong lành", style="natural"),
                TranslationCandidate("môi trường sạch, không khí trong lành", style="compact"),
            ],
            slot_seconds=2.0,
        )

        self.assertIsNotNone(selection.selected)
        self.assertEqual(selection.selected.style, "compact")
        self.assertFalse(selection.requires_review)

    def test_context_provider_generates_and_ranks_candidates_in_one_call(self) -> None:
        client = FixedLlmClient(
            responses=[
                '[{"segment_id":"0","candidates":['
                '{"style":"faithful","text":"Đây là một câu giải thích quá dài và vòng vo nên chắc chắn không thể đọc vừa khung thời gian này."},'
                '{"style":"natural","text":"Câu này nghe rất tự nhiên và vừa nhịp"},'
                '{"style":"compact","text":"Câu này vừa nhịp."}'
                ']}]'
            ]
        )
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            allow_machine_translate_recovery=False,
            max_rewrite_rounds=0,
        )

        rows = TranslationDraftBuilder(provider).build(
            [_beat(0)],
            preset=TranslationPreset.LITERAL_SAFE,
        )

        self.assertEqual(client.call_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].metadata["translation_v3"]["candidate_count"], 2)
        self.assertEqual(
            rows[0].metadata["translation_v3"]["requested_candidate_count"],
            2,
        )
        self.assertEqual(rows[0].metadata["translation_v3"]["selected_style"], "natural")

    def test_completed_blocks_resume_without_provider_calls(self) -> None:
        policy = TranslationV3Policy(max_core_beats=2, max_block_seconds=30.0)
        beats = [_beat(index) for index in range(4)]
        first_provider = _BlockProvider()
        captured: dict[str, list[dict]] = {}

        first = TranslationDraftBuilder(first_provider).build(
            beats,
            preset=TranslationPreset.LITERAL_SAFE,
            policy=policy,
            on_checkpoint=lambda block_id, rows, _current, _total: captured.__setitem__(
                block_id, [draft_to_checkpoint(row) for row in rows]
            ),
        )
        second_provider = _BlockProvider()
        second = TranslationDraftBuilder(second_provider).build(
            beats,
            preset=TranslationPreset.LITERAL_SAFE,
            policy=policy,
            checkpoint=captured,
        )

        self.assertEqual(first_provider.calls, 2)
        self.assertEqual(second_provider.calls, 0)
        self.assertEqual([row.translated_text for row in second], [row.translated_text for row in first])
        self.assertTrue(all(row.metadata["translation_checkpoint_status"] == "checkpoint_hit" for row in second))

    def test_fingerprint_binds_prompt_glossary_and_policy(self) -> None:
        beats = [_beat(0)]
        base = translation_run_fingerprint(
            beats,
            preset=TranslationPreset.LITERAL_SAFE,
            provider_identity={"provider": "fixed", "model": "m1"},
            user_prompt="faithful",
            glossary={},
        )
        changed = translation_run_fingerprint(
            beats,
            preset=TranslationPreset.LITERAL_SAFE,
            provider_identity={"provider": "fixed", "model": "m1"},
            user_prompt="natural",
            glossary={"花生油": "dầu lạc"},
        )
        self.assertNotEqual(base, changed)

    def test_quality_contract_distinguishes_review_and_blocked_rows(self) -> None:
        clean = TranslationDraftSegment(
            segment_index=0,
            translated_text="Bản dịch sạch",
            translation_preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=2.0,
            estimated_tts_duration_seconds=1.9,
            quality_flags=[],
            metadata={"provider": "fixed"},
        )
        blocked = TranslationDraftSegment(
            segment_index=1,
            translated_text="",
            translation_preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=2.0,
            estimated_tts_duration_seconds=0.0,
            quality_flags=["translation_gate_failed", "needs_operator_review"],
            metadata={"provider": "fixed"},
        )

        contract = build_translation_quality_contract([clean, blocked], total_count=2)

        self.assertEqual(contract["filled_count"], 1)
        self.assertEqual(contract["blocked_count"], 1)
        self.assertFalse(contract["complete"])
        self.assertFalse(contract["tts_ready"])

    def test_non_forced_identical_run_reuses_current_v3_rows(self) -> None:
        source_id = uuid4()
        workspace_id = uuid4()
        beat = SimpleNamespace(
            id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=2000,
            text="你好",
            normalized_text="你好",
            confidence=0.95,
            speaker_label="speaker_1",
            difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V2_RUN_1",
            status=TranscriptSegmentStatus.APPROVED,
        )
        db = MagicMock()
        service = AudioAnalysisService(
            db=db,
            storage=MagicMock(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
        )
        drafts = service._translation_drafts([beat])
        fingerprint = service._translation_fingerprint(
            drafts,
            preset=TranslationPreset.LITERAL_SAFE,
            builder=service.translation_builder,
            prompt=None,
            glossary={},
        )
        quality_contract = {
            "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
            "total_count": 1,
            "filled_count": 1,
            "blocked_count": 0,
            "review_required_count": 0,
            "complete": True,
            "tts_ready": True,
        }
        source = SimpleNamespace(
            id=source_id,
            workspace_id=workspace_id,
            metadata_json={
                "translation_v3_cache": {
                    "fingerprint": fingerprint,
                    "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                    "analysis_version": beat.analysis_version,
                    "quality_contract": quality_contract,
                }
            },
            source_platform="DOUYIN",
            source_video_external_id="source-v3-cache",
            source_profile=SimpleNamespace(
                source_profile_external_id="profile",
                handle="profile",
                display_name="Profile",
            ),
        )
        row = SimpleNamespace(
            segment_index=0,
            text="Xin chào",
            metadata_json={"translation_v3": {"run_fingerprint": fingerprint}},
            quality_flags_json={"flags": []},
        )
        db.scalars.side_effect = [[], [row], [row]]
        with (
            patch.object(service, "_load_source_video", return_value=source),
            patch.object(service, "get_transcript_segments", return_value=[beat]),
            patch.object(service, "get_summary", return_value={"asset_count": 1, "manifest": {"assets": []}}),
            patch(
                "src.audio_pipeline.services.audio_analysis_service.WorkspaceSettingsService.get_translation_user_prompt",
                return_value=None,
            ),
            patch.object(service.translation_builder, "build") as build,
        ):
            result = service.run_translation_only(source_id, force_refresh=False)

        build.assert_not_called()
        self.assertTrue(result.metrics["cache_hit"])
        self.assertEqual(result.translation_count, 1)

    def test_translation_job_returns_existing_active_single_flight(self) -> None:
        source_id = uuid4()
        source = SimpleNamespace(
            id=source_id,
            workspace_id=uuid4(),
            metadata_json={},
        )
        beat = SimpleNamespace(
            id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=1000,
            text="你好",
            normalized_text="你好",
            confidence=0.9,
            speaker_label=None,
            difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V2_RUN_1",
            status=TranscriptSegmentStatus.APPROVED,
        )
        active = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.BUILD_TRANSLATION_DRAFT,
            status=JobStatus.RUNNING,
            source_video_id=source_id,
        )
        db = MagicMock()
        db.scalar.return_value = active
        service = AudioAnalysisService(
            db=db,
            storage=MagicMock(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
        )
        with (
            patch.object(service, "_load_source_video", return_value=source),
            patch.object(service, "get_transcript_segments", return_value=[beat]),
            patch(
                "src.audio_pipeline.services.audio_analysis_service.WorkspaceSettingsService.get_translation_user_prompt",
                return_value=None,
            ),
            patch("src.audio_pipeline.services.audio_analysis_service.JobService.create_job") as create_job,
        ):
            result = service.create_translation_job(source_id)

        self.assertIs(result, active)
        create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
