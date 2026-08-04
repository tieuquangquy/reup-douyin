from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.api.routes.ocr import OcrCreateRequest, _summary_response, create_ocr_job
from src.enums import MediaAssetStatus, MediaAssetType
from src.services.quality_localization_service import (
    QUALITY_WORKFLOW_VERSION,
    QualityLocalizationError,
    QualityLocalizationService,
    _phase1_watchdog_timeout_seconds,
)


class _CreateService:
    def __init__(self) -> None:
        self.request = None

    def create_ocr_job(self, request):
        self.request = request
        return SimpleNamespace(id=uuid4(), status="QUEUED")


def test_phase1_watchdog_allows_long_postprocess_without_weakening_scan_timeout() -> None:
    settings = SimpleNamespace(
        phase1_no_progress_timeout_seconds=300,
        phase1_postprocess_no_progress_timeout_seconds=1_200,
    )

    assert _phase1_watchdog_timeout_seconds(settings, "phase1_scan") == 300
    assert (
        _phase1_watchdog_timeout_seconds(
            settings, "phase1_postprocess_local_text_gate"
        )
        == 1_200
    )


def test_phase1_postprocess_timeout_never_undercuts_scan_watchdog() -> None:
    settings = SimpleNamespace(
        phase1_no_progress_timeout_seconds=420,
        phase1_postprocess_no_progress_timeout_seconds=120,
    )

    assert (
        _phase1_watchdog_timeout_seconds(settings, "phase1_postprocess_merge_tracks")
        == 420
    )


def test_frontend_ocr_route_forces_quality_workflow_and_master_phase1() -> None:
    service = _CreateService()
    source_video_id = uuid4()

    response = create_ocr_job(
        OcrCreateRequest(source_video_id=source_video_id),
        service=service,
    )

    assert response.source_video_id == source_video_id
    assert service.request.workflow_version == QUALITY_WORKFLOW_VERSION
    assert service.request.use_master_phase1 is True
    assert service.request.clean_hardsub is True


def test_frontend_ocr_summary_exposes_visual_provenance_counts() -> None:
    source_video_id = uuid4()

    response = _summary_response(
        {
            "source_video_id": str(source_video_id),
            "provenance_counts": {
                "EDITOR_OVERLAY": 7,
                "SOURCE_INTRINSIC": 11,
                "UNCERTAIN": 2,
            },
            "protected_source_tracks": 11,
            "provenance_artifact_path": "visual_text_provenance_v2.json",
        }
    )

    assert response.provenance_counts["SOURCE_INTRINSIC"] == 11
    assert response.protected_source_tracks == 11
    assert response.provenance_artifact_path == "visual_text_provenance_v2.json"


def test_quality_summary_requires_audio_mix_approval_after_visual_approval(tmp_path) -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=workspace_id, metadata_json={})
    preview = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(scalar=lambda _query: preview)
    storage = SimpleNamespace(root=tmp_path.resolve())
    service = QualityLocalizationService(db, storage=storage)
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]

    (tmp_path / "phase4_visual_approval.json").write_text("{}", encoding="utf-8")
    approved = service.summary(source_id)
    assert approved["workflow_stage"] == "VISUAL_APPROVED"
    assert approved["visual_approved"] is True
    assert approved["can_render_final"] is False

    (tmp_path / "phase4_background_mix_approval.json").write_text(
        '{"status": "AUDIO_MIX_APPROVED"}', encoding="utf-8"
    )
    audio_approved = service.summary(source_id)
    assert audio_approved["workflow_stage"] == "AUDIO_APPROVED"
    assert audio_approved["can_render_final"] is True

    (tmp_path / "phase4_adaptive_final.mp4").write_bytes(b"final")
    final = service.summary(source_id)
    assert final["workflow_stage"] == "FINAL_READY"
    assert final["can_render_final"] is True


def test_quality_summary_exposes_hash_bound_residual_review_state(tmp_path) -> None:
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=uuid4(), metadata_json={})
    service = QualityLocalizationService(
        SimpleNamespace(scalar=lambda _query: None),
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]

    (tmp_path / "phase4_preflight_meta.json").write_text(
        json.dumps(
            {
                "status": "PHASE4_PREFLIGHT_BLOCKED",
                "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
                "residual_cjk": {
                    "detections": [
                        {"frame_index": 12, "text": "source residual", "confidence": 0.91}
                    ],
                    "source_confirmation_frames": ["qa/residual/frame_000012.jpg"],
                },
            }
        ),
        encoding="utf-8",
    )
    triage = service.summary(source_id)
    assert triage["workflow_stage"] == "WAITING_RESIDUAL_TRIAGE"
    assert triage["residual_review_objects"] == [
        {
            "content_id": "residual_001",
            "frame_index": 12,
            "text": "source residual",
            "confidence": 0.91,
            "image_path": "qa/residual/frame_000012.jpg",
        }
    ]

    (tmp_path / "phase2_residual_remediation_proposal_frontend.json").write_text(
        json.dumps(
            {
                "proposal_sha256": "a" * 64,
                "proposals": [{"remediation_id": "rem_001", "proposed_action": "ADD"}],
            }
        ),
        encoding="utf-8",
    )
    proposal = service.summary(source_id)
    assert proposal["workflow_stage"] == "WAITING_RESIDUAL_REVIEW"
    assert proposal["residual_proposal_sha256"] == "a" * 64
    assert proposal["residual_proposal_objects"][0]["remediation_id"] == "rem_001"


def test_quality_summary_accepts_verified_no_dialogue_audio_gate(tmp_path) -> None:
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=uuid4(), metadata_json={})
    service = QualityLocalizationService(
        SimpleNamespace(scalar=lambda _query: None),
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]
    (tmp_path / "phase4_visual_approval.json").write_text("{}", encoding="utf-8")
    (tmp_path / "phase4_no_dialogue_source_audio.wav").write_bytes(b"RIFFpreview")
    (tmp_path / "phase4_no_dialogue_audio_review.json").write_text(
        '{"status": "PENDING_AUDIO_REVIEW"}', encoding="utf-8"
    )

    pending = service.summary(source_id)
    assert pending["workflow_stage"] == "WAITING_AUDIO_REVIEW"
    assert pending["audio_mix_preview_path"] == "phase4_no_dialogue_source_audio.wav"
    assert pending["can_render_final"] is False

    (tmp_path / "phase4_audio_approval.json").write_text(
        '{"status": "AUDIO_APPROVED"}', encoding="utf-8"
    )
    approved = service.summary(source_id)
    assert approved["workflow_stage"] == "AUDIO_APPROVED"
    assert approved["can_render_final"] is True


def test_stage_audio_review_normalizes_verified_no_dialogue_duration(tmp_path) -> None:
    source_id = uuid4()
    source = SimpleNamespace(
        id=source_id,
        workspace_id=uuid4(),
        metadata_json={
            "dialogue_phase": "no_dialogue",
            "duration_seconds": 21.0,
            "vad": {
                "provider": "silero_vad",
                "difficulty_flags": ["silero_vad_executed", "no_speech_detected"],
                "metadata": {"speech_seconds": 0.0, "speech_segment_count": 0},
            },
        },
    )
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    (tmp_path / "phase4_visual_approval.json").write_text("{}", encoding="utf-8")
    db = SimpleNamespace(flush=lambda: None, commit=lambda: None)
    service = QualityLocalizationService(
        db, storage=SimpleNamespace(root=tmp_path.resolve())
    )
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]
    service._source_video_path = lambda _source_id: source_path  # type: ignore[method-assign]
    service._current_asset = lambda _source_id, _asset_type: None  # type: ignore[method-assign]
    service.summary = lambda _source_id: {"workflow_stage": "WAITING_AUDIO_REVIEW"}  # type: ignore[method-assign]

    with patch(
        "src.services.quality_localization_service.stage_verified_no_dialogue_audio_handoff"
    ) as stage:
        result = service.stage_audio_review(source_id, operator_id="operator")

    assert result["workflow_stage"] == "WAITING_AUDIO_REVIEW"
    metadata = stage.call_args.kwargs["analysis_metadata"]
    assert metadata["audio_input"]["source_video_duration_seconds"] == 21.0


def test_localization_artifact_path_blocks_traversal(tmp_path) -> None:
    source_id = uuid4()
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    service = object.__new__(QualityLocalizationService)
    service.active_root = lambda _source_id: root.resolve()  # type: ignore[method-assign]

    with pytest.raises(QualityLocalizationError):
        service.artifact_path(source_id, "../outside.txt")


def test_quality_summary_falls_back_to_closed_phase3_timeline_for_preview_retry(tmp_path) -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=workspace_id, metadata_json={})
    preview = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(scalar=lambda _query: preview)
    storage = SimpleNamespace(root=tmp_path.resolve())
    service = QualityLocalizationService(db, storage=storage)
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]

    (tmp_path / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
    (tmp_path / "phase3_review_queue.json").write_text(
        '{"content_objects": [], "review_summary": {"status": "TRANSLATION_APPROVED"}}',
        encoding="utf-8",
    )
    (tmp_path / "phase3_translation_timeline.json").write_text(
        '{"content_objects": [{"content_id": "c1", "zh_approved": "原文", "vi_text_candidate": "Bản nháp", "vi_text_approved": "Bản đã duyệt", "roles": ["generic"]}]}',
        encoding="utf-8",
    )

    summary = service.summary(source_id)
    assert summary["workflow_stage"] == "WAITING_VISUAL_REVIEW"
    assert summary["translation_objects"][0]["content_id"] == "c1"
    assert summary["translation_objects"][0]["vi_text_candidate"] == "Bản đã duyệt"


def test_phase1_retry_reuses_only_hash_bound_v58_authority(tmp_path) -> None:
    service = object.__new__(QualityLocalizationService)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    (tmp_path / "master_timeline.json").write_text("[]", encoding="utf-8")
    (tmp_path / "phase1_meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "visual_text_provenance_v2.json").write_text(
        '{"schema_version":"visual_text_provenance_v2","tracks":[]}',
        encoding="utf-8",
    )

    service._record_phase1_authority(tmp_path, source)
    assert service._phase1_is_reusable(tmp_path, source) is True

    (tmp_path / "master_timeline.json").write_text("[{\"changed\": true}]", encoding="utf-8")
    assert service._phase1_is_reusable(tmp_path, source) is False


def test_preview_retry_reuses_media_asset_when_storage_key_is_unchanged(tmp_path) -> None:
    workspace_id = uuid4()
    source = SimpleNamespace(id=uuid4(), workspace_id=workspace_id)
    job_id = uuid4()
    preview = tmp_path / "run" / "phase4_adaptive_visual_preview.mp4"
    preview.parent.mkdir()
    preview.write_bytes(b"encoded-preview")
    existing = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        source_video_id=source.id,
        asset_type=MediaAssetType.CLEANED_VIDEO,
        status=MediaAssetStatus.AVAILABLE,
        version=2,
        is_current=True,
        storage_key="run/phase4_adaptive_visual_preview.mp4",
        relative_path="run/phase4_adaptive_visual_preview.mp4",
        manifest_group="quality_visual_preview",
        created_by_job_id=uuid4(),
        mime_type="video/mp4",
        size_bytes=1,
        checksum_sha256="0" * 64,
        metadata_json={},
        error_message="old error",
    )
    db = MagicMock()
    # max(version), then lookup by the unique workspace/storage key.
    db.scalar.side_effect = [2, existing]
    storage = SimpleNamespace(root=tmp_path.resolve(), provider_name="local")
    service = QualityLocalizationService(db, storage=storage)

    rebound = service._register_workspace_file(
        source,
        preview,
        asset_type=MediaAssetType.CLEANED_VIDEO,
        manifest_group="quality_visual_preview",
        job_id=job_id,
        metadata={"workflow_version": QUALITY_WORKFLOW_VERSION},
    )

    assert rebound is existing
    assert not db.add.called
    assert existing.version == 2
    assert existing.is_current is True
    assert existing.created_by_job_id == job_id
    assert existing.size_bytes == len(b"encoded-preview")
    assert existing.error_message is None


def test_visual_preview_cache_requires_current_v12_pass_artifact(tmp_path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    input_path = root / "phase4_render_input.json"
    input_path.write_text('{"render_tracks": []}', encoding="utf-8")
    output = root / "phase4_adaptive_visual_preview.mp4"
    output.write_bytes(b"encoded-preview")
    remediation = {"path": "remediation.json", "sha256": "a" * 64, "materialization_sha256": "b" * 64}
    (root / "phase4_visual_remediation_active.json").write_text(
        json.dumps({"active_ref": remediation}), encoding="utf-8"
    )
    qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    qa_path.parent.mkdir()
    qa_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "residual_cjk": {
                    "policy_version": "source_intrinsic_cjk_v12_temporal_provenance",
                    "detections": [],
                },
            }
        ),
        encoding="utf-8",
    )
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "phase4_adaptive_render_meta.json").write_text(
        json.dumps(
            {
                "status": "VISUAL_PREVIEW_RENDERED",
                "output_qa_status": "PASS",
                "phase4_input_sha256": digest(input_path),
                "output_video_sha256": digest(output),
                "visual_remediation_ref": remediation,
                "artifacts": {
                    "video": output.name,
                    "output_qa": "qa/phase4_adaptive_visual_preview_output_qa.json",
                },
            }
        ),
        encoding="utf-8",
    )

    service = object.__new__(QualityLocalizationService)
    assert service._visual_preview_is_reusable(root) is True

    (root / "phase4_render_input.json").write_text('{"render_tracks": [1]}', encoding="utf-8")
    assert service._visual_preview_is_reusable(root) is False


def test_final_cache_requires_complete_narration_and_hash_bound_pass(tmp_path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    contract = root / "phase4_render_input.json"
    contract.write_text('{"final_render_gate": "READY_FOR_FINAL_RENDER"}', encoding="utf-8")
    final = root / "phase4_adaptive_final.mp4"
    final.write_bytes(b"final")
    qa = root / "qa" / "phase4_adaptive_final_output_qa.json"
    qa.parent.mkdir()
    qa.write_text('{"status": "PASS", "failed_checks": []}', encoding="utf-8")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    meta_path = root / "phase4_adaptive_render_meta.json"
    meta = {
        "status": "FINAL_RENDERED",
        "output_qa_status": "PASS",
        "audio_mix": {"narration_complete": True},
        "output_video_sha256": digest(final),
        "phase4_input_sha256": digest(contract),
        "source_video_sha256": digest(source),
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    service = object.__new__(QualityLocalizationService)
    service._source_video_path = lambda _source_id: source  # type: ignore[method-assign]

    assert service._final_output_is_reusable(root, uuid4()) is True

    meta["audio_mix"]["narration_complete"] = False
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert service._final_output_is_reusable(root, uuid4()) is False
