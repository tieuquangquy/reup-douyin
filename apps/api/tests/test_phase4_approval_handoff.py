from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.media_pipeline.video_renderer.phase4_approvals import (
    apply_residual_cjk_false_positive_approval,
    Phase4ApprovalError,
    approve_background_mix_review,
    approve_uncertain_dialogue_audio_review,
    approve_verified_no_dialogue_audio_handoff,
    attach_background_and_approve,
    load_residual_cjk_false_positive_approval,
    prepare_approved_audio_handoff,
    record_residual_cjk_false_positive_approval,
    record_visual_approval,
    stage_audio_handoff,
    stage_background_mix_review,
    stage_uncertain_dialogue_audio_review,
    stage_verified_no_dialogue_audio_handoff,
)

from src.media_pipeline.video_renderer.phase4_approvals import residual_detection_sha256


def test_cluster_bound_single_glyph_accepts_bounded_geometry_variation() -> None:
    approved_detection = {
        "frame_index": 100,
        "text": "\u798f",
        "geometry": {"x": 0.48, "y": 0.55, "width": 0.03, "height": 0.08},
    }
    approved_hash = residual_detection_sha256(approved_detection)
    approved = {
        "schema_version": "phase4_residual_cjk_false_positive_approval_v2",
        "approval_sha256": "a" * 64,
        "approvals": [
            {
                "cluster_id": "cluster_1",
                "detection": {
                    "frame_index": 100,
                    "text": "福",
                    "geometry": {"x": 0.48, "y": 0.55, "width": 0.03, "height": 0.08},
                },
                "detection_sha256": approved_hash,
                "cluster_detection_sha256s": [approved_hash, "c" * 64],
            }
        ],
    }
    detection = {
        "frame_index": 106,
        "text": "福",
        "geometry": {"x": 0.48, "y": 0.55, "width": 0.03, "height": 0.05},
    }

    blocking, excluded = apply_residual_cjk_false_positive_approval(
        [detection], approved
    )

    assert blocking == []
    assert excluded[0]["approval_match"]["type"] == "TEMPORAL_GEOMETRY_CLUSTER"
from src.storage.local import LocalStorageBackend, to_windows_long_path


class Phase4ApprovalHandoffTests(unittest.TestCase):
    def test_residual_false_positive_approval_is_bound_to_immutable_evidence(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = root / "phase3_render_handoff.json"
            handoff.write_text("{}", encoding="utf-8")
            handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
            detection = {
                "frame_index": 685,
                "text": "22.2å…ƒ",
                "confidence": 0.9589,
                "geometry": {"x": 0.26, "y": 0.33, "width": 0.04, "height": 0.02},
            }
            (root / "phase4_preflight_meta.json").write_text(
                json.dumps(
                    {
                        "phase3_render_handoff_sha256": handoff_sha,
                        "residual_cjk": {"detections": [detection]},
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_render_input_preview.json").write_text(
                json.dumps(
                    {"refs": {"source_video_ref": {"sha256": "s" * 64}}}
                ),
                encoding="utf-8",
            )
            evidence = (
                root
                / "qa"
                / "phase4_preflight_samples"
                / "frame_000685_before_mask_after.jpg"
            )
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"visual evidence")

            approval = record_residual_cjk_false_positive_approval(
                root_dir=root,
                frame_index=685,
                approval_token="OCR_FALSE_POSITIVE_CONFIRMED_CASE_V1",
                operator_id="operator",
            )

            self.assertEqual(
                approval["status"], "OCR_FALSE_POSITIVE_CONFIRMED"
            )
            immutable = root / approval["evidence_ref"]["path"]
            self.assertTrue(immutable.is_file())
            self.assertEqual(
                hashlib.sha256(immutable.read_bytes()).hexdigest(),
                approval["evidence_ref"]["sha256"],
            )
            loaded = load_residual_cjk_false_positive_approval(
                root_dir=root,
                contract={
                    "refs": {"source_video_ref": {"sha256": "s" * 64}}
                },
            )
            self.assertEqual(loaded["approval_sha256"], approval["approval_sha256"])

    def test_residual_false_positive_loader_rejects_detection_tampering(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = root / "phase3_render_handoff.json"
            handoff.write_text("{}", encoding="utf-8")
            handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
            detection = {
                "frame_index": 685,
                "text": "22.2Ã¥â€¦Æ’",
                "confidence": 0.9589,
                "geometry": {"x": 0.26, "y": 0.33, "width": 0.04, "height": 0.02},
            }
            (root / "phase4_preflight_meta.json").write_text(
                json.dumps(
                    {
                        "phase3_render_handoff_sha256": handoff_sha,
                        "residual_cjk": {"detections": [detection]},
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_render_input_preview.json").write_text(
                json.dumps(
                    {"refs": {"source_video_ref": {"sha256": "s" * 64}}}
                ),
                encoding="utf-8",
            )
            evidence = (
                root
                / "qa"
                / "phase4_preflight_samples"
                / "frame_000685_before_mask_after.jpg"
            )
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"visual evidence")
            approval = record_residual_cjk_false_positive_approval(
                root_dir=root,
                frame_index=685,
                approval_token="OCR_FALSE_POSITIVE_CONFIRMED_CASE_V1",
                operator_id="operator",
            )
            approval["detection"]["text"] = "tampered"
            (root / "phase4_residual_cjk_false_positive_approval.json").write_text(
                json.dumps(approval), encoding="utf-8"
            )

            with self.assertRaises(Phase4ApprovalError):
                load_residual_cjk_false_positive_approval(
                    root_dir=root,
                    contract={
                        "refs": {"source_video_ref": {"sha256": "s" * 64}}
                    },
                )

    def test_audio_handoff_verifies_hash_copies_asset_and_persists_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            narration = root / "incoming.wav"
            narration.write_bytes(b"RIFF-approved-narration")
            digest = hashlib.sha256(narration.read_bytes()).hexdigest()
            background = root / "background.wav"
            background.write_bytes(b"RIFF-background")
            background_digest = hashlib.sha256(background.read_bytes()).hexdigest()
            manifest = {
                "manifest_version": "RENDER_PREP_MANIFEST_V2",
                "audio_review": {"status": "PENDING_AUDIO_REVIEW"},
                "current_outputs": {
                    "joined_narration": [
                        {
                            "storage_key": "storage/audio.wav",
                            "sha256": digest,
                            "mime_type": "audio/wav",
                        }
                    ],
                    "background_audio": [
                        {
                            "storage_key": "storage/background.wav",
                            "sha256": background_digest,
                            "mime_type": "audio/wav",
                        }
                    ],
                },
            }
            result = prepare_approved_audio_handoff(
                root_dir=root,
                manifest=manifest,
                narration_path=narration,
                background_path=background,
                operator_id="local_operator",
            )
            approved = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(approved["audio_review"]["status"], "AUDIO_APPROVED")
            self.assertEqual(
                approved["current_outputs"]["joined_narration"][0]["sha256"],
                digest,
            )
            self.assertTrue((root / "phase4_joined_narration.wav").is_file())
            self.assertTrue((root / "phase4_background.wav").is_file())
            self.assertEqual(result["status"], "AUDIO_APPROVED")

    def test_audio_handoff_rejects_hash_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            narration = root / "incoming.wav"
            narration.write_bytes(b"wrong")
            manifest = {
                "manifest_version": "RENDER_PREP_MANIFEST_V2",
                "audio_review": {"status": "PENDING_AUDIO_REVIEW"},
                "current_outputs": {
                    "joined_narration": [
                        {"storage_key": "audio.wav", "sha256": "a" * 64}
                    ]
                },
            }
            with self.assertRaises(Phase4ApprovalError):
                prepare_approved_audio_handoff(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=narration,
                    operator_id="local_operator",
                )

    def test_audio_handoff_retry_does_not_rewrite_approved_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            narration = root / "incoming.wav"
            narration.write_bytes(b"RIFF-approved-narration")
            digest = hashlib.sha256(narration.read_bytes()).hexdigest()
            manifest = {
                "manifest_version": "RENDER_PREP_MANIFEST_V2",
                "audio_review": {"status": "PENDING_AUDIO_REVIEW"},
                "current_outputs": {
                    "joined_narration": [
                        {
                            "storage_key": narration.name,
                            "sha256": digest,
                            "mime_type": "audio/wav",
                        }
                    ]
                },
            }
            first = prepare_approved_audio_handoff(
                root_dir=root,
                manifest=manifest,
                narration_path=narration,
                operator_id="local_operator",
            )
            manifest_path = root / "render_prep_manifest.json"
            approval_path = root / "phase4_audio_approval.json"
            before = (manifest_path.read_bytes(), approval_path.read_bytes())

            second = prepare_approved_audio_handoff(
                root_dir=root,
                manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
                narration_path=root / "phase4_joined_narration.wav",
                operator_id="local_operator",
            )

            self.assertEqual(second, first)
            self.assertEqual(
                (manifest_path.read_bytes(), approval_path.read_bytes()), before
            )

    def test_audio_staging_accepts_long_background_storage_path(self) -> None:
        with TemporaryDirectory() as tmp:
            try:
                root = Path(tmp)
                narration = root / "joined.wav"
                narration.write_bytes(b"RIFF-narration")
                storage = LocalStorageBackend(tmp)
                key = "/".join(["stem_" + "x" * 72] * 4) + "/background.wav"
                write = storage.write_bytes(key, b"RIFF-background" * 8)
                manifest = {
                    "manifest_version": "RENDER_PREP_MANIFEST_V2",
                    "current_outputs": {
                        "joined_narration": [
                            {
                                "storage_key": narration.name,
                                "sha256": hashlib.sha256(
                                    narration.read_bytes()
                                ).hexdigest(),
                            }
                        ],
                        "background_audio": [
                            {
                                "storage_key": key,
                                "sha256": write.checksum_sha256,
                            }
                        ],
                    },
                }

                result = stage_audio_handoff(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=narration,
                    background_path=storage.resolve(key).absolute_path,
                )

                self.assertTrue(result["background_staged"])
                self.assertTrue((root / "phase4_background.wav").is_file())
                self.assertEqual(
                    hashlib.sha256(
                        (root / "phase4_background.wav").read_bytes()
                    ).hexdigest(),
                    write.checksum_sha256,
                )
            finally:
                shutil.rmtree(to_windows_long_path(Path(tmp)), ignore_errors=True)

    def test_attach_background_preserves_narration_and_binds_new_stem(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            narration = root / "phase4_joined_narration.wav"
            narration.write_bytes(b"RIFF-approved-narration")
            narration_digest = hashlib.sha256(narration.read_bytes()).hexdigest()
            background = root / "no_vocals.wav"
            background.write_bytes(b"RIFF" + (b"background-stem" * 8))
            manifest = {
                "manifest_version": "RENDER_PREP_MANIFEST_V2",
                "audio_review": {"status": "AUDIO_APPROVED"},
                "current_outputs": {
                    "joined_narration": [
                        {
                            "storage_key": narration.name,
                            "sha256": narration_digest,
                            "mime_type": "audio/wav",
                        }
                    ],
                    "background_audio": [],
                },
                "render_contract": {
                    "audio_strategy": "replace_with_timeline_aligned_vietnamese_narration"
                },
            }
            result = attach_background_and_approve(
                root_dir=root,
                manifest=manifest,
                narration_path=narration,
                background_path=background,
                operator_id="local_operator",
            )
            approved = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["narration_ref"]["sha256"], narration_digest)
            self.assertIsNotNone(result["background_ref"])
            self.assertEqual(
                approved["render_contract"]["audio_strategy"],
                "mix_vietnamese_narration_with_background_stem",
            )
            self.assertTrue((root / "phase4_background.wav").is_file())
            self.assertTrue((root / "phase4_background_attachment.json").is_file())

    def test_visual_approval_requires_passing_output_qa(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "preview.mp4"
            qa = root / "qa" / "output_qa.json"
            qa.parent.mkdir()
            video.write_bytes(b"video")
            qa.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            approval = record_visual_approval(
                root_dir=root,
                video_path=video,
                output_qa_path=qa,
                operator_id="local_operator",
            )
            self.assertEqual(approval["status"], "VISUAL_APPROVED")
            self.assertEqual(
                approval["output_qa_ref"]["path"], "qa/output_qa.json"
            )
            self.assertTrue((root / "phase4_visual_approval.json").is_file())

    def test_uncertain_dialogue_review_stages_hash_bound_audition_stems(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = root / "phase4_adaptive_visual_preview.mp4"
            preview.write_bytes(b"preview-with-source-audio")
            qa = root / "qa" / "output_qa.json"
            qa.parent.mkdir()
            qa.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            record_visual_approval(
                root_dir=root,
                video_path=preview,
                output_qa_path=qa,
                operator_id="operator",
            )
            source_hash = "a" * 64
            (root / "phase4_render_input.json").write_text(
                json.dumps(
                    {"refs": {"source_video_ref": {"sha256": source_hash}}}
                ),
                encoding="utf-8",
            )
            vocals = root / "incoming_vocals.wav"
            background = root / "incoming_background.wav"
            vocals.write_bytes(b"RIFF" + b"v" * 100)
            background.write_bytes(b"RIFF" + b"b" * 100)
            analysis = {
                "analysis_version": "AUDIO_ANALYSIS_V1_RUN_1",
                "dialogue_phase": "dialogue_uncertain",
                "audio_input": {"source_video_id": "source-1"},
                "vad": {
                    "provider": "silero_vad",
                    "has_speech": True,
                    "difficulty_flags": ["silero_vad_executed"],
                    "metadata": {
                        "speech_seconds": 9.0,
                        "audio_seconds": 10.0,
                        "speech_segment_count": 2,
                    },
                },
                "separation": {
                    "difficulty_flags": [
                        "asr_empty_despite_vad_speech",
                        "needs_operator_review",
                    ]
                },
                "stt_provider": "funasr_paraformer",
            }

            review = stage_uncertain_dialogue_audio_review(
                root_dir=root,
                analysis_metadata=analysis,
                vocals_path=vocals,
                background_path=background,
                source_video_id="source-1",
                source_video_sha256=source_hash,
                required_dialogue_present_token="DIALOGUE_PRESENT_CASE",
                required_no_dialogue_token="NO_DIALOGUE_CASE",
            )

            self.assertEqual(review["status"], "PENDING_DIALOGUE_OPERATOR_REVIEW")
            self.assertFalse(review["operator_approval_written"])
            self.assertEqual(
                review["required_decision_tokens"]["no_dialogue"],
                "NO_DIALOGUE_CASE",
            )
            self.assertTrue(
                (root / "phase4_dialogue_uncertain_vocals.wav").is_file()
            )
            self.assertTrue(
                (root / "phase4_dialogue_uncertain_background.wav").is_file()
            )
            self.assertTrue(
                (root / "phase4_dialogue_detection_review.json").is_file()
            )
            approval = approve_uncertain_dialogue_audio_review(
                root_dir=root,
                approval_token="DIALOGUE_PRESENT_CASE",
                operator_id="operator",
            )
            self.assertEqual(approval["status"], "DIALOGUE_PRESENT_CONFIRMED")
            self.assertTrue(approval["operator_approval_written"])
            self.assertTrue(
                (root / "phase4_dialogue_detection_approval.json").is_file()
            )

    def test_background_mix_stages_review_and_archives_narration_only_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            narration = root / "incoming.wav"
            background = root / "incoming_background.wav"
            narration.write_bytes(b"RIFF-narration")
            background.write_bytes(b"RIFF-background" * 8)
            narration_hash = hashlib.sha256(narration.read_bytes()).hexdigest()
            (root / "phase4_audio_approval.json").write_text(
                json.dumps({"status": "AUDIO_APPROVED"}), encoding="utf-8"
            )
            manifest = {
                "manifest_version": "RENDER_PREP_MANIFEST_V2",
                "source_video": {"duration_seconds": 4.0},
                "audio_review": {
                    "status": "AUDIO_APPROVED",
                    "approved_at": "now",
                    "operator_id": "operator",
                    "narration_sha256": narration_hash,
                },
                "current_outputs": {
                    "joined_narration": [
                        {
                            "storage_key": "storage/narration.wav",
                            "sha256": narration_hash,
                            "mime_type": "audio/wav",
                        }
                    ],
                    "background_audio": [],
                },
                "render_contract": {"audio_strategy": "narration_only"},
            }

            def fake_run(command):
                Path(command[-1]).write_bytes(b"RIFF" + (b"mix-preview" * 8))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            result = stage_background_mix_review(
                root_dir=root,
                manifest=manifest,
                narration_path=narration,
                background_path=background,
                background_gain=1.0,
                run=fake_run,
            )

            self.assertEqual(result["status"], "PENDING_AUDIO_MIX_REVIEW")
            self.assertFalse(result["operator_approval_written"])
            self.assertFalse((root / "phase4_audio_approval.json").exists())
            self.assertTrue((root / "phase4_audio_mix_preview.wav").is_file())
            staged_manifest = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                staged_manifest["render_contract"]["background_gain"], 1.0
            )
            self.assertEqual(result["mix_recipe"]["background_gain"], 1.0)
            staged = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                staged["audio_review"]["status"], "PENDING_AUDIO_MIX_REVIEW"
            )
            approval = approve_background_mix_review(
                root_dir=root,
                approval_token="AUDIO_MIX_APPROVED",
                operator_id="operator",
            )
            self.assertEqual(approval["status"], "AUDIO_MIX_APPROVED")
            self.assertTrue(approval["operator_approval_written"])
            self.assertTrue((root / "phase4_audio_approval.json").is_file())
            self.assertTrue(
                (root / "phase4_background_mix_approval.json").is_file()
            )

    def test_measured_no_dialogue_stages_source_audio_without_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"source-video-with-audio")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            analysis = {
                "analysis_version": "AUDIO_ANALYSIS_V1_RUN_3",
                "dialogue_phase": "no_dialogue",
                "audio_input": {"source_video_duration_seconds": 12.5},
                "vad": {
                    "provider": "silero_vad",
                    "difficulty_flags": [
                        "silero_vad_executed",
                        "skip_dubbing",
                        "no_speech_detected",
                    ],
                    "metadata": {
                        "speech_seconds": 0.0,
                        "speech_segment_count": 0,
                    },
                },
            }

            def fake_run(command):
                Path(command[-1]).write_bytes(b"RIFF" + (b"source-audio" * 8))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            result = stage_verified_no_dialogue_audio_handoff(
                root_dir=root,
                source_video_path=source,
                analysis_metadata=analysis,
                source_video_id="source-id",
                required_approval_token="AUDIO_APPROVED_CASE",
                expected_source_sha256=source_hash,
                run=fake_run,
            )
            manifest = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["status"], "PENDING_AUDIO_REVIEW")
            self.assertFalse(result["operator_approval_written"])
            self.assertEqual(
                manifest["current_outputs"]["joined_narration"][0]["role"],
                "verified_no_dialogue_source_audio",
            )
            self.assertEqual(manifest["audio_review"]["status"], "PENDING_AUDIO_REVIEW")
            self.assertFalse((root / "phase4_audio_approval.json").exists())

            with self.assertRaises(Phase4ApprovalError):
                approve_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    approval_token="WRONG_TOKEN",
                    operator_id="operator",
                )
            approval = approve_verified_no_dialogue_audio_handoff(
                root_dir=root,
                approval_token="AUDIO_APPROVED_CASE",
                operator_id="operator",
            )
            self.assertEqual(approval["status"], "AUDIO_APPROVED")
            self.assertEqual(
                approval["audio_role"], "verified_no_dialogue_source_audio"
            )
            approved_review = json.loads(
                (root / "phase4_no_dialogue_audio_review.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(approved_review["operator_approval_written"])

    def test_no_dialogue_staging_rejects_unmeasured_or_spoken_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            analysis = {
                "dialogue_phase": "no_dialogue",
                "audio_input": {"source_video_duration_seconds": 4.0},
                "vad": {
                    "provider": "silero_vad",
                    "difficulty_flags": ["silero_vad_executed"],
                    "metadata": {
                        "speech_seconds": 1.0,
                        "speech_segment_count": 1,
                    },
                },
            }
            with self.assertRaises(Phase4ApprovalError):
                stage_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    source_video_path=source,
                    analysis_metadata=analysis,
                    source_video_id="source-id",
                    required_approval_token="AUDIO_APPROVED_CASE",
                )


if __name__ == "__main__":
    unittest.main()
