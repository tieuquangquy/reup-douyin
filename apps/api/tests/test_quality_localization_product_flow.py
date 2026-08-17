from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.audio_analysis import approve_source_video_translation_draft
from src.api.routes.ocr import OcrCreateRequest, _summary_response, create_ocr_job
from src.enums import MediaAssetStatus, MediaAssetType, TranscriptSegmentStatus
from src.media_pipeline.video_renderer.phase4_input_contract import Phase4InputError
from src.schemas.audio_analysis import ApproveTranslationDraftRequest
from src.services.quality_localization_service import (
    QUALITY_WORKFLOW_VERSION,
    QualityLocalizationError,
    QualityLocalizationService,
    _build_residual_proposal_checked,
    _matching_active_residual_remediation,
    _phase1_watchdog_timeout_seconds,
    _residual_translation_input_sha256,
)
from scripts.materialize_phase2_residual_remediation import (
    _sha256_json as remediation_sha256,
    activate_cumulative_remediation,
)


class _CreateService:
    def __init__(self) -> None:
        self.request = None

    def create_ocr_job(self, request):
        self.request = request
        return SimpleNamespace(id=uuid4(), status="QUEUED")


def test_matching_active_residual_remediation_resumes_same_proposal(tmp_path) -> None:
    proposal_sha = "a" * 64
    delta = {
        "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
        "proposal_ref": {"proposal_sha256": proposal_sha},
        "authority_refs": {},
        "approved_occurrences": [],
        "approved_geometry_overrides": [],
    }
    delta["remediation_sha256"] = remediation_sha256(delta)
    active_path, _ = activate_cumulative_remediation(
        root_dir=tmp_path,
        delta=delta,
    )

    assert _matching_active_residual_remediation(
        tmp_path, proposal_sha256=proposal_sha
    ) == active_path
    assert (
        _matching_active_residual_remediation(
            tmp_path, proposal_sha256="b" * 64
        )
        is None
    )


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


def test_frontend_ocr_route_rejects_repeated_analysis_at_translation_gate() -> None:
    source_video_id = uuid4()
    service = MagicMock()
    service.db = MagicMock()
    with patch(
        "src.api.routes.ocr.QualityLocalizationService"
    ) as quality_service:
        quality_service.return_value.summary.return_value = {
            "requires_dialogue_translation_approval": True,
            "dialogue_translation_blocked_count": 86,
        }
        with pytest.raises(HTTPException) as exc_info:
            create_ocr_job(
                OcrCreateRequest(source_video_id=source_video_id),
                service=service,
            )

    assert exc_info.value.status_code == 409
    assert "re-analysis is not required" in str(exc_info.value.detail)
    service.create_ocr_job.assert_not_called()


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
            "analysis_mode": "AUDIO_GUIDED_VISUAL",
            "audio_window_count": 4,
            "visual_trigger_count": 9,
            "all_frame_proxy_size": [288, 512],
        }
    )

    assert response.provenance_counts["SOURCE_INTRINSIC"] == 11
    assert response.protected_source_tracks == 11
    assert response.provenance_artifact_path == "visual_text_provenance_v2.json"
    assert response.analysis_mode == "AUDIO_GUIDED_VISUAL"
    assert response.audio_window_count == 4
    assert response.visual_trigger_count == 9
    assert response.all_frame_proxy_size == [288, 512]


def test_summary_exposes_dialogue_translation_blocker_instead_of_phase2_ready(
    tmp_path,
) -> None:
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, metadata_json={})
    db = MagicMock()
    db.get.return_value = source
    db.scalar.return_value = None
    service = QualityLocalizationService(
        db,
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    root = tmp_path / "run"
    root.mkdir()
    (root / "phase2_meta.json").write_text(
        json.dumps(
            {
                "tracks": 12,
                "content_objects": 7,
                "ready_for_phase3": False,
                "handoff_status": "HANDOFF_BLOCKED",
            }
        ),
        encoding="utf-8",
    )
    (root / "phase2_review_queue.json").write_text(
        json.dumps({"content_objects": []}), encoding="utf-8"
    )
    (root / "phase2_handoff_preview.json").write_text(
        json.dumps(
            {
                "status": "HANDOFF_BLOCKED",
                "blocked_reasons": [
                    "semantic_dialogue_translation_unapproved:ocr_content_001",
                    "semantic_dialogue_translation_unapproved:ocr_content_002",
                ],
            }
        ),
        encoding="utf-8",
    )

    with patch.object(service, "active_root", return_value=root):
        summary = service.summary(source_id)

    assert summary["workflow_stage"] == "WAITING_DIALOGUE_TRANSLATION_APPROVAL"
    assert summary["requires_dialogue_translation_approval"] is True
    assert summary["dialogue_translation_blocked_count"] == 2
    assert summary["phase2_content_object_count"] == 7
    response = _summary_response(
        {"source_video_id": str(source_id), **summary}
    )
    assert response.dialogue_translation_blocked_count == 2


def test_translation_approval_enqueues_cache_first_ocr_resume() -> None:
    source_id = uuid4()
    resume_job_id = uuid4()
    db = MagicMock()
    with (
        patch(
            "src.api.routes.audio_analysis.TranscriptEditService"
        ) as transcript_service,
        patch(
            "src.services.reup_pipeline_orchestrator.ReupPipelineOrchestrator"
        ) as orchestrator,
        patch(
            "src.services.quality_localization_service.QualityLocalizationService"
        ) as quality_service,
        patch(
            "src.ocr_pipeline.services.ocr_service.OcrPipelineService"
        ) as ocr_service,
    ):
        transcript_service.return_value.approve_translation_draft.return_value = {
            "approved_segments": 20,
            "binding_sha256": "a" * 64,
        }
        orchestrator.return_value.resume_translation_approved_items.return_value = (
            0,
            None,
        )
        quality_service.return_value.summary.return_value = {
            "requires_dialogue_translation_approval": True
        }
        ocr_service.return_value.create_ocr_job.return_value = SimpleNamespace(
            id=resume_job_id
        )

        response = approve_source_video_translation_draft(
            source_id,
            ApproveTranslationDraftRequest(),
            db,
        )

    assert response.ocr_resume_job_id == resume_job_id
    request = ocr_service.return_value.create_ocr_job.call_args.args[0]
    assert request.workflow_action == "resume_dialogue_translation"
    assert request.force_refresh is False
    assert request.use_master_phase1 is True
    db.commit.assert_called_once()


def test_phase1_candidate_seed_binds_current_audio_authority(tmp_path) -> None:
    source_id = uuid4()
    rows = [
        SimpleNamespace(
            segment_index=0,
            start_ms=500,
            end_ms=1_500,
            confidence=0.94,
            status=TranscriptSegmentStatus.APPROVED,
            text="你好",
            analysis_version="AUDIO_ANALYSIS_V5_RUN_9",
        ),
        SimpleNamespace(
            segment_index=1,
            start_ms=1_500,
            end_ms=2_000,
            confidence=0.80,
            status=TranscriptSegmentStatus.REJECTED,
            text="rejected",
            analysis_version="AUDIO_ANALYSIS_V5_RUN_9",
        ),
        SimpleNamespace(
            segment_index=2,
            start_ms=2_000,
            end_ms=2_000,
            confidence=0.80,
            status=TranscriptSegmentStatus.DRAFT,
            text="invalid timing",
            analysis_version="AUDIO_ANALYSIS_V5_RUN_9",
        ),
    ]
    db = SimpleNamespace(
        scalars=lambda _query: SimpleNamespace(all=lambda: rows)
    )
    service = QualityLocalizationService(
        db,
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    source = SimpleNamespace(
        id=source_id,
        duration_seconds=3.0,
        metadata_json={
            "has_speech": True,
            "vad": {"has_speech": True},
            "audio_analysis_cache": {
                "analysis_version": "AUDIO_ANALYSIS_V5_RUN_9",
                "fingerprint": "audio-fingerprint",
            },
        },
    )

    path, payload = service._build_phase1_candidate_seed(
        source=source,
        root_hint=tmp_path,
        job_id=uuid4(),
    )

    assert path.is_file()
    assert payload["mode"] == "AUDIO_GUIDED_VISUAL"
    assert payload["vad_has_speech"] is True
    assert payload["audio_analysis_version"] == "AUDIO_ANALYSIS_V5_RUN_9"
    assert payload["audio_analysis_fingerprint"] == "audio-fingerprint"
    assert payload["segments_count"] == 1
    assert payload["rejected_segments_count"] == 1
    assert payload["invalid_segments_count"] == 1
    assert payload["windows"]


def test_phase1_candidate_seed_fails_closed_when_speech_has_no_timing(tmp_path) -> None:
    service = QualityLocalizationService(
        SimpleNamespace(
            scalars=lambda _query: SimpleNamespace(all=lambda: [])
        ),
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    source = SimpleNamespace(
        id=uuid4(),
        duration_seconds=3.0,
        metadata_json={"has_speech": True, "vad": {"has_speech": True}},
    )

    with pytest.raises(QualityLocalizationError, match="re-run Analyze Audio"):
        service._build_phase1_candidate_seed(
            source=source,
            root_hint=tmp_path,
            job_id=uuid4(),
        )


def test_phase1_candidate_seed_allows_verified_no_dialogue_visual_only(tmp_path) -> None:
    service = QualityLocalizationService(
        SimpleNamespace(
            scalars=lambda _query: SimpleNamespace(all=lambda: [])
        ),
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    source = SimpleNamespace(
        id=uuid4(),
        duration_seconds=3.0,
        metadata_json={"has_speech": False, "vad": {"has_speech": False}},
    )

    _, payload = service._build_phase1_candidate_seed(
        source=source,
        root_hint=tmp_path,
        job_id=uuid4(),
    )

    assert payload["mode"] == "VISUAL_ONLY"
    assert payload["vad_has_speech"] is False
    assert payload["windows"] == []


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
    (tmp_path / "phase4_render_input_preview.json").write_text(
        json.dumps({"video": {"frame_width": 720, "frame_height": 1280}}),
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
    translation_input_sha256 = _residual_translation_input_sha256(
        triage["residual_review_objects"],
        authority_sha256=triage["residual_authority_sha256"],
    )
    (tmp_path / "phase2_residual_translation_suggestions.json").write_text(
        json.dumps(
            {
                "schema_version": "phase2_residual_translation_suggestions_v2",
                "status": "SUGGESTION_ONLY",
                "operator_approval_written": False,
                "residual_authority_sha256": triage["residual_authority_sha256"],
                "input_sha256": translation_input_sha256,
                "suggestions": [
                    {
                        "ocr_text": "source residual",
                        "ocr_text_corrected": "corrected residual",
                        "vi_text_suggested": "bản dịch còn sót",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    translated = service.summary(source_id)
    assert translated["residual_translation_status"] == "READY"
    assert translated["residual_translation_input_sha256"] == translation_input_sha256
    assert translated["residual_translation_suggestion_count"] == 1
    assert translated["residual_review_objects"][0][
        "ocr_text_corrected_suggested"
    ] == "corrected residual"
    assert translated["residual_review_objects"][0]["vi_text_suggested"] == (
        "bản dịch còn sót"
    )

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


def test_residual_translation_job_batches_and_caches_current_authority(tmp_path) -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    job_id = uuid4()
    authority_sha256 = "a" * 64
    residual_rows = [
        {"content_id": "residual_001", "frame_index": 10, "text": "耐看气质妆"},
        {"content_id": "residual_002", "frame_index": 20, "text": "教程"},
    ]
    input_sha256 = _residual_translation_input_sha256(
        residual_rows,
        authority_sha256=authority_sha256,
    )
    owner_job = SimpleNamespace(
        payload_json={
            "residual_authority_sha256": authority_sha256,
            "residual_translation_input_sha256": input_sha256,
        }
    )
    source = SimpleNamespace(
        id=source_id,
        workspace_id=workspace_id,
        metadata_json={},
    )
    db = SimpleNamespace(
        get=lambda _model, _id: owner_job,
        flush=lambda: None,
        commit=lambda: None,
    )
    service = QualityLocalizationService(
        db,
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]
    service.summary = lambda _source_id: {  # type: ignore[method-assign]
        "workflow_stage": "WAITING_RESIDUAL_TRIAGE",
        "residual_authority_sha256": authority_sha256,
        "residual_review_objects": residual_rows,
    }
    translated_rows = [
        {
            "ocr_text": "耐看气质妆",
            "ocr_text_corrected": "耐看气质妆",
            "vi_text_suggested": "Trang điểm thanh lịch",
        },
        {
            "ocr_text": "教程",
            "ocr_text_corrected": "教程",
            "vi_text_suggested": "Hướng dẫn",
        },
    ]

    with patch(
        "src.services.quality_auto_policy.translate_residual_texts",
        return_value=translated_rows,
    ) as translate:
        service.run_residual_review(
            source_video_id=source_id,
            job_id=job_id,
            action="suggest_residual_translation",
            suggestions=None,
            proposal_sha256=None,
            operator_id="frontend_operator",
        )

    translate.assert_called_once()
    artifact = json.loads(
        (tmp_path / "phase2_residual_translation_suggestions.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["status"] == "SUGGESTION_ONLY"
    assert artifact["operator_approval_written"] is False
    assert artifact["residual_authority_sha256"] == authority_sha256
    assert artifact["input_sha256"] == input_sha256
    assert artifact["suggestions"] == translated_rows

    with patch(
        "src.services.quality_auto_policy.translate_residual_texts"
    ) as translate_again:
        service.run_residual_review(
            source_video_id=source_id,
            job_id=job_id,
            action="suggest_residual_translation",
            suggestions=None,
            proposal_sha256=None,
            operator_id="frontend_operator",
        )
    translate_again.assert_not_called()


def test_quality_summary_prioritizes_current_encoded_output_residual(tmp_path) -> None:
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=uuid4(), metadata_json={})
    service = QualityLocalizationService(
        SimpleNamespace(scalar=lambda _query: None),
        storage=SimpleNamespace(root=tmp_path.resolve()),
    )
    service._source = lambda _source_id: source  # type: ignore[method-assign]
    service.active_root = lambda _source_id: tmp_path.resolve()  # type: ignore[method-assign]
    (tmp_path / "phase4_preflight_meta.json").write_text(
        json.dumps({"status": "READY_FOR_PHASE4", "final_render_gate": "READY_FOR_FINAL_RENDER", "residual_cjk": {"detections": []}}),
        encoding="utf-8",
    )
    render_input = tmp_path / "phase4_render_input.json"
    render_input.write_text(json.dumps({"status": "READY_FOR_PHASE4"}), encoding="utf-8")
    preview = tmp_path / "phase4_adaptive_visual_preview.mp4"
    preview.write_bytes(b"encoded-preview")
    (tmp_path / "phase4_adaptive_render_meta.json").write_text(
        json.dumps({
            "status": "VISUAL_PREVIEW_QA_FAILED",
            "output_qa_status": "FAIL",
            "output_qa_failed_checks": ["residual_cjk"],
            "phase4_input_sha256": hashlib.sha256(render_input.read_bytes()).hexdigest(),
            "output_video_sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
            "artifacts": {"video": preview.name},
        }),
        encoding="utf-8",
    )
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "phase4_adaptive_visual_preview_output_qa.json").write_text(
        json.dumps({
            "status": "FAIL",
            "failed_checks": ["residual_cjk"],
            "residual_cjk": {
                "complete": True,
                "detections": [{"frame_index": 77, "text": "中文", "confidence": 0.8}],
            },
        }),
        encoding="utf-8",
    )
    summary = service.summary(source_id)
    assert summary["workflow_stage"] == "WAITING_RESIDUAL_TRIAGE"
    assert summary["encoded_output_qa_current"] is True
    assert summary["residual_authority_source"] == "encoded_visual_preview_output_qa"
    assert summary["residual_review_objects"][0]["frame_index"] == 77


def test_quality_summary_handles_blocked_preflight_without_final_render_input(
    tmp_path,
) -> None:
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
                    "complete": True,
                    "detections": [
                        {"frame_index": 42, "text": "中文", "confidence": 0.9}
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "phase4_adaptive_render_meta.json").write_text(
        json.dumps(
            {
                "status": "VISUAL_PREVIEW_QA_FAILED",
                "output_qa_status": "FAIL",
                "output_qa_failed_checks": ["residual_cjk"],
                "phase4_input_sha256": "f" * 64,
                "output_video_sha256": "e" * 64,
                "artifacts": {"video": "phase4_adaptive_visual_preview.mp4"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "phase4_adaptive_visual_preview.mp4").write_bytes(b"stale-preview")

    summary = service.summary(source_id)

    assert summary["workflow_stage"] == "WAITING_RESIDUAL_TRIAGE"
    assert summary["encoded_output_qa_current"] is False
    assert summary["residual_authority_source"] == "phase4_preflight"


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


def test_phase1_retry_reuses_only_hash_bound_temporal_authority(tmp_path) -> None:
    service = object.__new__(QualityLocalizationService)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    (tmp_path / "master_timeline.json").write_text("[]", encoding="utf-8")
    (tmp_path / "phase1_meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "visual_text_provenance_v2.json").write_text(
        '{"schema_version":"visual_text_provenance_v2","tracks":[]}',
        encoding="utf-8",
    )
    (tmp_path / "phase1_candidate_windows_v1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "phase1_event_metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "phase1_track_coverage_v2.json").write_text(
        '{"schema_version":"phase1_track_coverage_v2","tracks":[]}',
        encoding="utf-8",
    )

    service._record_phase1_authority(
        tmp_path,
        source,
        analysis_engine="audio_visual_temporal_v1",
        candidate_seed_sha256="seed",
    )
    assert service._phase1_is_reusable(
        tmp_path,
        source,
        analysis_engine="audio_visual_temporal_v1",
        candidate_seed_sha256="seed",
    ) is True

    (tmp_path / "master_timeline.json").write_text("[{\"changed\": true}]", encoding="utf-8")
    assert service._phase1_is_reusable(
        tmp_path,
        source,
        analysis_engine="audio_visual_temporal_v1",
        candidate_seed_sha256="seed",
    ) is False


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


def test_residual_proposal_wraps_phase4_contract_error(tmp_path) -> None:
    with patch(
        "src.services.quality_localization_service.build_residual_remediation_proposal",
        side_effect=Phase4InputError("Invalid timing/geometry for sub_71"),
    ):
        with pytest.raises(QualityLocalizationError) as caught:
            _build_residual_proposal_checked(tmp_path)

    assert caught.value.code == "PHASE4_INPUT_INVALID"
    assert "sub_71" in str(caught.value)


def test_phase2_remediation_runtime_error_has_terminal_contract_code(tmp_path) -> None:
    service = object.__new__(QualityLocalizationService)
    service._write_semantic_dialogue_authority = lambda *_args, **_kwargs: None
    with patch(
        "src.services.quality_localization_service.run_phase2_only.main",
        side_effect=RuntimeError(
            "Residual remediation geometry override is unsafe"
        ),
    ):
        with pytest.raises(QualityLocalizationError) as caught:
            service._run_phase2_with_semantic_authority(
                source=object(),
                root=tmp_path,
                video_path=tmp_path / "source.mp4",
            )

    assert caught.value.code == "PHASE2_REMEDIATION_INVALID"
