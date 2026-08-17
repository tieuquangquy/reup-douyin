from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.enums import JobType
from src.services.frontend_core_runtime import (
    FRONTEND_STAGE_RUNTIME_KEY,
    FrontendCoreRuntimeError,
    assert_expected_stage_version,
    assert_job_frontend_runtime,
    bind_job_to_frontend_runtime,
    ensure_job_frontend_runtime,
    frontend_stage_runtime,
    frontend_stage_versions,
)


class FrontendCoreRuntimeTests(unittest.TestCase):
    def test_latest_seven_frontend_stage_versions_are_explicit(self) -> None:
        self.assertEqual(
            frontend_stage_versions(),
            {
                "DOWNLOAD_VIDEO": "DOWNLOAD_V2",
                "ANALYZE_AUDIO": "AUDIO_ANALYSIS_V5",
                "BUILD_TRANSLATION_DRAFT": "TRANSLATION_V5",
                "SYNTHESIZE_TTS": "TTS_TEMPORAL_V6",
                "ANALYZE_OCR": "OCR-V34",
                "RENDER_PREVIEW": "QUALITY_LOCALIZATION_V24_1",
                "RENDER_FINAL": "RENDER_PIPELINE_V1",
            },
        )

    def test_render_jobs_are_runtime_bound(self) -> None:
        for job_type, version in (
            (JobType.RENDER_PREVIEW, "QUALITY_LOCALIZATION_V24_1"),
            (JobType.RENDER_FINAL, "RENDER_PIPELINE_V1"),
        ):
            job = SimpleNamespace(
                job_type=job_type,
                payload_json={"source_video_id": "video-1"},
                context_json=None,
                metadata_json=None,
            )
            contract = bind_job_to_frontend_runtime(job)
            self.assertIsNotNone(contract)
            self.assertEqual(contract["stage_version"], version)
            self.assertEqual(assert_job_frontend_runtime(job), contract)

    def test_current_stage_contracts_keep_the_optimized_components(self) -> None:
        download = frontend_stage_runtime(JobType.DOWNLOAD_VIDEO)
        audio = frontend_stage_runtime(JobType.ANALYZE_AUDIO)
        translation = frontend_stage_runtime(JobType.BUILD_TRANSLATION_DRAFT)
        tts = frontend_stage_runtime(JobType.SYNTHESIZE_TTS)

        self.assertEqual(download["recipe_version"], "download-quality-policy-v2")
        self.assertEqual(download["components"]["post_download_qa"], "post-download-qa-v1")
        self.assertEqual(audio["recipe_version"], "audio-analysis-v5-selective-dialogue-validation1")
        self.assertEqual(
            translation["recipe_version"],
            "translation-v3-contextual-semantic-utterance-ranking-6",
        )
        self.assertEqual(tts["stage_version"], "TTS_TEMPORAL_V6")
        self.assertEqual(
            tts["components"]["whole_video_alignment"],
            "whole-video-silence-alignment-v2",
        )
        self.assertEqual(tts["recipe_version"], "context-aware-tts-director-v2")

    def test_current_stage_contracts_keep_the_optimized_components(self) -> None:
        download = frontend_stage_runtime(JobType.DOWNLOAD_VIDEO)
        audio = frontend_stage_runtime(JobType.ANALYZE_AUDIO)
        translation = frontend_stage_runtime(JobType.BUILD_TRANSLATION_DRAFT)
        tts = frontend_stage_runtime(JobType.SYNTHESIZE_TTS)

        self.assertEqual(download["recipe_version"], "download-quality-policy-v2")
        self.assertEqual(download["components"]["post_download_qa"], "post-download-qa-v1")
        self.assertEqual(audio["recipe_version"], "audio-analysis-v5-selective-dialogue-validation1")
        self.assertEqual(
            translation["recipe_version"],
            "translation-v3-contextual-semantic-utterance-ranking-6",
        )
        self.assertEqual(tts["stage_version"], "TTS_TEMPORAL_V6")
        self.assertEqual(tts["recipe_version"], "context-aware-tts-director-v2")

    def test_new_job_is_bound_in_payload_context_and_metadata(self) -> None:
        job = SimpleNamespace(
            job_type=JobType.ANALYZE_AUDIO,
            payload_json={"source_video_id": "video-1"},
            context_json=None,
            metadata_json={"progress_authority": "audio_subphase"},
        )
        contract = bind_job_to_frontend_runtime(job)

        self.assertIsNotNone(contract)
        self.assertEqual(job.payload_json[FRONTEND_STAGE_RUNTIME_KEY], contract)
        self.assertEqual(job.context_json[FRONTEND_STAGE_RUNTIME_KEY], contract)
        self.assertEqual(job.metadata_json[FRONTEND_STAGE_RUNTIME_KEY], contract)
        self.assertEqual(job.metadata_json["runtime_version"], "AUDIO_ANALYSIS_V5")
        self.assertEqual(assert_job_frontend_runtime(job), contract)

    def test_stale_browser_expectation_is_rejected(self) -> None:
        with self.assertRaises(FrontendCoreRuntimeError):
            assert_expected_stage_version(JobType.ANALYZE_OCR, "OCR-V29")

    def test_stale_persisted_binding_is_never_silently_upgraded(self) -> None:
        current = frontend_stage_runtime(JobType.SYNTHESIZE_TTS)
        assert current is not None
        stale = {**current, "stage_version": "TTS_TEMPORAL_V3"}
        job = SimpleNamespace(
            job_type=JobType.SYNTHESIZE_TTS,
            payload_json={FRONTEND_STAGE_RUNTIME_KEY: stale},
            context_json=None,
            metadata_json=None,
        )

        with self.assertRaises(FrontendCoreRuntimeError):
            ensure_job_frontend_runtime(job)
        self.assertEqual(
            job.payload_json[FRONTEND_STAGE_RUNTIME_KEY]["stage_version"],
            "TTS_TEMPORAL_V3",
        )

    def test_unversioned_legacy_job_is_bound_once_before_execution(self) -> None:
        job = SimpleNamespace(
            job_type=JobType.DOWNLOAD_VIDEO,
            payload_json={},
            context_json=None,
            metadata_json=None,
        )
        first = ensure_job_frontend_runtime(job)
        second = ensure_job_frontend_runtime(job)

        self.assertEqual(first, second)
        self.assertEqual(first["stage_version"], "DOWNLOAD_V2")

    def test_started_legacy_job_is_not_silently_upgraded(self) -> None:
        job = SimpleNamespace(
            job_type=JobType.ANALYZE_OCR,
            payload_json={},
            context_json=None,
            metadata_json=None,
            steps=[SimpleNamespace(status="COMPLETED")],
        )

        with self.assertRaises(FrontendCoreRuntimeError):
            ensure_job_frontend_runtime(job)


if __name__ == "__main__":
    unittest.main()
