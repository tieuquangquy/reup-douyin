"""Product orchestration for the operator-gated V24.1 localization pipeline.

The regression scripts remain thin CLI adapters.  This service is the product
boundary used by durable frontend jobs and deliberately invokes those same phase
implementations against a persistent per-run workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from scripts import (
    run_phase2_only,
    run_phase3_only,
    run_phase4_adaptive,
    run_phase4_preflight,
)
from scripts.apply_phase3_review_proposal import (
    Phase3ProposalApprovalError,
    apply_review_proposal,
)
from scripts.build_phase3_review_proposal import (
    Phase3ReviewProposalError,
    build_review_proposal,
)
from scripts.build_phase2_residual_remediation_proposal import (
    ResidualRemediationProposalError,
    build_proposal as build_residual_remediation_proposal,
    validate_proposal as validate_residual_remediation_proposal,
)
from scripts.materialize_phase2_residual_remediation import (
    ResidualRemediationMaterializationError,
    activate_cumulative_remediation,
    materialize_remediation,
    verify_remediation,
)
from scripts.rebind_phase3_approvals_after_residual_remediation import (
    Phase3ApprovalRebindError,
    rebind_approvals as rebind_phase3_approvals,
    stage_unapproved_placeholders,
)
from src.core.settings import get_settings
from src.enums import (
    JobStatus,
    JobType,
    MediaAssetStatus,
    MediaAssetType,
    TranscriptSegmentStatus,
)
from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    approve_background_mix_review,
    approve_verified_no_dialogue_audio_handoff,
    attach_background_and_approve,
    prepare_approved_audio_handoff,
    record_visual_approval,
    stage_audio_handoff,
    stage_background_mix_review,
    stage_verified_no_dialogue_audio_handoff,
)
from src.models.ingestion import SourceVideo
from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.media import MediaAsset
from src.models.jobs import Job
from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    EVENT_SCAN_ENGINE_VERSION,
    EVENT_SCAN_POLICY_VERSION,
    build_audio_candidate_windows,
)
from src.services.phase2_operator_review import apply_phase2_operator_review
from src.services.job_service import JobService
from src.services.quality_auto_policy import (
    AUTO_QUALITY_ACTOR,
    AUTO_QUALITY_POLICY_VERSION,
    QualityAutoPolicyBlocked,
    build_ocr_decisions,
)
from src.services.residual_translation import (
    RESIDUAL_NORMALIZATION_VERSION,
    normalize_residual_detections,
    translation_authority_suggestions,
)
from src.storage.local import LocalStorageBackend


QUALITY_WORKFLOW_VERSION = "QUALITY_LOCALIZATION_V24_1"
QUALITY_ANALYSIS_ENGINE = EVENT_SCAN_ENGINE_VERSION
QUALITY_ANALYSIS_POLICY = EVENT_SCAN_POLICY_VERSION
QUALITY_METADATA_KEY = "quality_localization"
ProgressCallback = Callable[[str, int | None], None]


class QualityLocalizationError(RuntimeError):
    pass


def _phase1_watchdog_timeout_seconds(settings: Any, phase: str) -> int:
    """Return the bounded no-progress window for the active Phase-1 stage."""

    scan_timeout = max(
        60,
        int(getattr(settings, "phase1_no_progress_timeout_seconds", 300) or 300),
    )
    if not str(phase or "").startswith("phase1_postprocess"):
        return scan_timeout
    return max(
        scan_timeout,
        int(
            getattr(
                settings,
                "phase1_postprocess_no_progress_timeout_seconds",
                1_200,
            )
            or 1_200
        ),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _residual_translation_input_sha256(
    residual_rows: list[Mapping[str, Any]],
    *,
    authority_sha256: str,
) -> str:
    return _sha256_json(
        {
            "schema_version": "residual_translation_input_v2_temporal_content",
            "normalization_version": RESIDUAL_NORMALIZATION_VERSION,
            "authority_sha256": str(authority_sha256 or ""),
            "rows": [
                {
                    "content_id": str(row.get("content_id") or ""),
                    "text": str(row.get("text") or "").strip(),
                    "start_frame": row.get("start_frame", row.get("frame_index")),
                    "end_frame": row.get("end_frame", row.get("frame_index")),
                    "geometry": {
                        key: round(float(dict(row.get("geometry") or {}).get(key) or 0.0), 6)
                        for key in ("x", "y", "width", "height")
                    },
                }
                for row in residual_rows
            ],
        }
    )


def _read_object(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise QualityLocalizationError(f"Required artifact is missing: {path.name}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityLocalizationError(f"Invalid artifact: {path.name}") from exc
    if not isinstance(payload, dict):
        raise QualityLocalizationError(f"Artifact must contain an object: {path.name}")
    return payload


def _require_phase2_ready_for_phase3(root: Path, *, operation: str) -> None:
    """Reject a blocked Phase-2 delta at its real workflow boundary."""

    meta = _read_object(root / "phase2_meta.json", required=False)
    handoff = _read_object(root / "phase2_handoff.json", required=False)
    if (
        bool(meta.get("ready_for_phase3"))
        and str(handoff.get("status") or "") == "READY_FOR_PHASE3"
    ):
        return
    preview = _read_object(root / "phase2_handoff_preview.json", required=False)
    reasons = [str(value) for value in preview.get("blocked_reasons") or [] if str(value)]
    detail = ", ".join(reasons[:6]) or str(meta.get("status") or "not_ready")
    raise QualityLocalizationError(
        f"{operation} is blocked before Phase 3: {detail}"
    )


def _matching_active_residual_remediation(
    root: Path,
    *,
    proposal_sha256: str,
) -> Path | None:
    """Return a verified active delta when a retry repeats its proposal.

    Materialization intentionally changes Phase-2 authority, so the original
    proposal becomes stale immediately after a successful delta. A crashed
    worker must resume from the active remediation instead of validating and
    materializing that proposal a second time.
    """

    from src.services.residual_remediation_authority import (
        ResidualRemediationAuthorityError,
        resolve_active_residual_remediation,
    )

    try:
        active_path = resolve_active_residual_remediation(root)
    except ResidualRemediationAuthorityError as exc:
        raise QualityLocalizationError(str(exc)) from exc
    if active_path is None:
        return None
    active = _read_object(active_path)
    if not verify_remediation(active):
        raise QualityLocalizationError(
            "Active residual remediation self-hash is invalid"
        )
    active_proposal_sha256 = str(
        dict(active.get("proposal_ref") or {}).get("proposal_sha256") or ""
    )
    if active_proposal_sha256 != str(proposal_sha256 or ""):
        return None
    return active_path


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


class QualityLocalizationService:
    def __init__(
        self,
        db: Session,
        *,
        storage: LocalStorageBackend | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)

    def create_run_root(self, source_video_id: UUID, job_id: UUID) -> Path:
        source = self._source(source_video_id)
        root = (
            self.storage.root
            / "quality-localization"
            / str(source.workspace_id)
            / str(source.id)
            / str(job_id)
        ).resolve()
        if not root.is_relative_to(self.storage.root):
            raise QualityLocalizationError("Localization workspace escaped storage root")
        return root

    def create_preview_job(
        self,
        source_video_id: UUID,
        *,
        translations: list[Mapping[str, Any]] | None,
        operator_id: str,
        auto_approve: bool = False,
    ):
        from src.services.pipeline_recipe_runtime import (
            bind_job_to_current_recipe,
            bind_job_to_recipe_reference,
        )

        source = self._source(source_video_id)
        job = JobService(self.db).create_job(
            job_type=JobType.RENDER_PREVIEW,
            workspace_id=source.workspace_id,
            source_video_id=source.id,
            payload_json={
                "source_video_id": str(source.id),
                "workflow_version": QUALITY_WORKFLOW_VERSION,
                "workflow_action": "translation_review_and_preview",
                "translations": [dict(row) for row in list(translations or [])],
                "operator_id": str(operator_id or "frontend_operator"),
                "auto_approve": bool(auto_approve),
                "auto_quality_policy_version": (
                    AUTO_QUALITY_POLICY_VERSION if auto_approve else None
                ),
            },
            idempotency_key=None,
        )
        quality_state = dict(dict(source.metadata_json or {}).get(QUALITY_METADATA_KEY) or {})
        recipe_reference = quality_state.get("pipeline_recipe_lock")
        if isinstance(recipe_reference, dict) and recipe_reference:
            bind_job_to_recipe_reference(job, recipe_reference)
        else:
            bind_job_to_current_recipe(job)
        self.db.commit()
        return job

    def create_residual_review_job(
        self,
        source_video_id: UUID,
        *,
        action: str,
        suggestions: list[Mapping[str, Any]] | None = None,
        proposal_sha256: str | None = None,
        operator_id: str,
        auto_approve: bool = False,
    ):
        from src.services.pipeline_recipe_runtime import bind_job_to_recipe_reference

        source = self._source(source_video_id)
        state = dict(dict(source.metadata_json or {}).get(QUALITY_METADATA_KEY) or {})
        recipe_reference = state.get("pipeline_recipe_lock")
        if not isinstance(recipe_reference, dict) or not recipe_reference:
            raise QualityLocalizationError("Quality workflow has no bound recipe")
        mode = str(action or "")
        idempotency_key: str | None = None
        residual_authority_sha256: str | None = None
        residual_translation_input_sha256: str | None = None
        if mode == "suggest_residual_translation":
            summary = self.summary(source.id)
            residual_rows = [
                dict(row)
                for row in list(summary.get("residual_review_objects") or [])
                if isinstance(row, Mapping)
            ]
            residual_authority_sha256 = str(
                summary.get("residual_authority_sha256") or ""
            ).strip()
            if not residual_rows or not residual_authority_sha256:
                raise QualityLocalizationError(
                    "Residual translation requires current residual OCR authority"
                )
            residual_translation_input_sha256 = _residual_translation_input_sha256(
                residual_rows,
                authority_sha256=residual_authority_sha256,
            )
            idempotency_key = (
                f"residual-translate:{source.id}:"
                f"{residual_authority_sha256[:24]}:"
                f"{residual_translation_input_sha256}"
            )
            existing = self.db.scalar(
                select(Job)
                .where(
                    Job.workspace_id == source.workspace_id,
                    Job.idempotency_key == idempotency_key,
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                if existing.status in {
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.RETRYABLE,
                    JobStatus.WAITING_FOR_REVIEW,
                }:
                    return existing
                if (
                    existing.status == JobStatus.COMPLETED
                    and str(summary.get("residual_translation_status") or "")
                    == "READY"
                    and str(
                        summary.get("residual_translation_input_sha256") or ""
                    )
                    == residual_translation_input_sha256
                ):
                    return existing
                # Keep the terminal job for audit while releasing the logical key
                # so an operator retry can enqueue the exact same authority again.
                existing.idempotency_key = (
                    f"{idempotency_key}:retired:{str(existing.id)[:12]}"
                )
                self.db.flush()
        job = JobService(self.db).create_job(
            job_type=JobType.RENDER_PREVIEW,
            workspace_id=source.workspace_id,
            source_video_id=source.id,
            payload_json={
                "source_video_id": str(source.id),
                "workflow_version": QUALITY_WORKFLOW_VERSION,
                "workflow_action": str(action),
                "suggestions": [dict(row) for row in list(suggestions or [])],
                "proposal_sha256": str(proposal_sha256 or ""),
                "operator_id": str(operator_id or "frontend_operator"),
                "auto_approve": bool(auto_approve),
                "auto_quality_policy_version": (
                    AUTO_QUALITY_POLICY_VERSION if auto_approve else None
                ),
                "residual_authority_sha256": residual_authority_sha256,
                "residual_translation_input_sha256": (
                    residual_translation_input_sha256
                ),
            },
            idempotency_key=idempotency_key,
        )
        bind_job_to_recipe_reference(job, recipe_reference)
        self.db.commit()
        return job

    def active_root(self, source_video_id: UUID) -> Path:
        source = self._source(source_video_id)
        state = dict(dict(source.metadata_json or {}).get(QUALITY_METADATA_KEY) or {})
        relative = str(state.get("active_root") or "").strip()
        root = (self.storage.root / relative).resolve()
        if (
            not relative
            or not root.is_relative_to(self.storage.root)
            or not root.is_dir()
        ):
            raise QualityLocalizationError(
                "No persistent quality-localization workspace is available"
            )
        return root

    def run_phase12(
        self,
        *,
        source_video_id: UUID,
        job_id: UUID,
        action: str = "analyze",
        decisions: list[Mapping[str, Any]] | None = None,
        operator_id: str = "frontend_operator",
        force_refresh: bool = False,
        analysis_engine: str = QUALITY_ANALYSIS_ENGINE,
        auto_advance: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        from src.models.jobs import Job

        recipe_reference: dict[str, Any] | None = None
        analyze_recipe_reference: dict[str, Any] | None = None
        owner_job = self.db.get(Job, job_id)
        if owner_job is not None:
            owner_payload = dict(owner_job.payload_json or {})
            candidate = owner_payload.get("pipeline_recipe_lock")
            if isinstance(candidate, dict) and candidate:
                recipe_reference = dict(candidate)
            analyze_candidate = owner_payload.get("analyze_ocr_recipe_lock")
            if isinstance(analyze_candidate, dict) and analyze_candidate:
                analyze_recipe_reference = dict(analyze_candidate)
        video_path = self._source_video_path(source.id)
        requested_mode = str(action or "analyze")
        # Translation approval only invalidates the semantic Phase-2 bridge;
        # Phase 1 remains hash-bound and reusable.  Keep a distinct durable job
        # action for observability while executing the normal cache-first path.
        mode = (
            "analyze"
            if requested_mode == "resume_dialogue_translation"
            else requested_mode
        )

        def progress(phase: str, percent: int) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        phase2_already_approved = False
        if mode == "analyze":
            selected_engine = str(analysis_engine or QUALITY_ANALYSIS_ENGINE)
            candidate_seed_path, candidate_seed = self._build_phase1_candidate_seed(
                source=source,
                root_hint=self.storage.root,
                job_id=job_id,
            )
            candidate_seed_sha256 = str(candidate_seed.get("seed_sha256") or "")
            root: Path | None = None
            if not force_refresh:
                try:
                    candidate = self.active_root(source.id)
                except QualityLocalizationError:
                    candidate = None
                if candidate is not None and self._phase1_is_reusable(
                    candidate,
                    video_path,
                    analysis_engine=selected_engine,
                    candidate_seed_sha256=candidate_seed_sha256,
                ):
                    root = candidate
            if root is None:
                root = self.create_run_root(source.id, job_id)
            if self._phase1_is_reusable(
                root,
                video_path,
                analysis_engine=selected_engine,
                candidate_seed_sha256=candidate_seed_sha256,
            ):
                progress("phase1_reused", 40)
            else:
                progress("phase1_candidate_discovery", 3)

                def phase1_progress(phase: str, current: int, total: int) -> None:
                    ratio = max(0.0, min(1.0, float(current) / max(1.0, float(total))))
                    if phase in {
                        "phase1_scan",
                        "phase1_event_scan",
                        "phase1_resume_decode",
                    }:
                        percent = 3 + int(ratio * 22)
                    elif phase == "phase1_event_detect":
                        percent = 25 + int(ratio * 7)
                    elif phase == "phase1_dense_rescan":
                        percent = 32 + int(ratio * 3)
                    elif phase == "phase1_small_text_recovery":
                        percent = 35 + int(ratio * 2)
                    elif phase.startswith("phase1_postprocess"):
                        percent = 37 + int(ratio * 2)
                    elif phase == "phase1_coverage_closure":
                        percent = 39 + int(ratio * 2)
                    elif phase == "phase1_unassigned_discovery":
                        percent = 41 + int(ratio * 3)
                    elif phase == "phase1_coverage_reclosure":
                        percent = 44 + int(ratio)
                    else:
                        percent = 39
                    progress(f"{phase}|{current}|{total}", percent)

                if self._run_phase1_subprocess(
                    video_path=video_path,
                    root=root,
                    on_progress=phase1_progress,
                    analysis_engine=selected_engine,
                    candidate_windows_path=candidate_seed_path,
                ) != 0:
                    raise QualityLocalizationError(
                        f"Phase 1 {selected_engine} failed"
                    )
                self._record_phase1_authority(
                    root,
                    video_path,
                    analysis_engine=selected_engine,
                    candidate_seed_sha256=candidate_seed_sha256,
                )
            candidate_seed_path.unlink(missing_ok=True)
            progress("phase1_complete", 45)
            self._set_active_root(
                source,
                root,
                stage="PHASE1_COMPLETE",
                recipe_reference=recipe_reference,
                analyze_recipe_reference=analyze_recipe_reference,
            )
        elif mode == "approve_ocr":
            root = self.active_root(source.id)
            # Approval is durable and may be retried after a provider/Phase 3
            # failure.  The first attempt closes phase2_review_queue.json;
            # replaying the same payload against that empty queue used to
            # raise "decisions must cover every current review object" and
            # turn a recoverable retry into a terminal failure.
            phase2_queue = _read_object(root / "phase2_review_queue.json", required=False)
            queue_rows = [
                row for row in list(phase2_queue.get("content_objects") or [])
                if isinstance(row, Mapping)
            ]
            if queue_rows:
                self._write_phase2_decisions(
                    root,
                    decisions=list(decisions or []),
                    operator_id=operator_id,
                )
            phase2_meta_current = _read_object(root / "phase2_meta.json", required=False)
            phase2_already_approved = (
                not queue_rows
                and bool(phase2_meta_current.get("ready_for_phase3"))
                and (root / "phase2_handoff.json").is_file()
            )
            if not queue_rows and not phase2_already_approved:
                raise QualityLocalizationError(
                    "OCR decisions are unavailable and Phase 2 is not approved"
                )
            progress("phase2_decisions_applied", 15)
        else:
            raise QualityLocalizationError(f"Unsupported OCR workflow action: {mode}")

        if phase2_already_approved:
            progress("phase2_reused", 88)
        else:
            progress("phase2_local_ocr", 50)
            if self._run_phase2_with_semantic_authority(
                source=source,
                root=root,
                video_path=video_path,
            ) != 0:
                raise QualityLocalizationError("Phase 2 local OCR failed")
        progress("phase2_persist", 88)
        self._persist_phase2_db(source, root, job_id=job_id)
        if auto_advance and mode == "analyze":
            auto_queue = _read_object(
                root / "phase2_review_queue.json", required=False
            )
            auto_rows = [
                dict(row)
                for row in list(auto_queue.get("content_objects") or [])
                if isinstance(row, Mapping)
            ]
            if auto_rows:
                try:
                    auto_decisions = build_ocr_decisions(auto_rows)
                except QualityAutoPolicyBlocked as exc:
                    _write_json_atomic(
                        root / "quality_auto_decision_authority.json",
                        {
                            "schema_version": "quality_auto_decision_authority_v1",
                            "policy_version": AUTO_QUALITY_POLICY_VERSION,
                            "status": "BLOCKED",
                            "stage": "OCR",
                            "reason": str(exc),
                            "created_at": _now(),
                        },
                    )
                else:
                    progress("auto_ocr_decisions", 89)
                    self._write_phase2_decisions(
                        root,
                        decisions=auto_decisions,
                        operator_id=AUTO_QUALITY_ACTOR,
                    )
                    if self._run_phase2_with_semantic_authority(
                        source=source,
                        root=root,
                        video_path=video_path,
                    ) != 0:
                        raise QualityLocalizationError(
                            "Auto-approved Phase 2 materialization failed"
                        )
                    self._persist_phase2_db(source, root, job_id=job_id)
                    _write_json_atomic(
                        root / "quality_auto_decision_authority.json",
                        {
                            "schema_version": "quality_auto_decision_authority_v1",
                            "policy_version": AUTO_QUALITY_POLICY_VERSION,
                            "status": "APPROVED",
                            "stage": "OCR",
                            "decision_count": len(auto_decisions),
                            "created_at": _now(),
                        },
                    )
        phase2_meta = _read_object(root / "phase2_meta.json")
        if bool(phase2_meta.get("ready_for_phase3")):
            progress("phase3_translation_draft", 92)
            if run_phase3_only.main([str(root)]) != 0:
                raise QualityLocalizationError("Phase 3 translation draft failed")
        summary = self.summary(source.id)
        self._set_active_root(
            source,
            root,
            stage=str(summary["workflow_stage"]),
            recipe_reference=recipe_reference,
            analyze_recipe_reference=analyze_recipe_reference,
        )
        progress("completed", 100)
        self.db.commit()
        return summary

    def run_translation_and_preview(
        self,
        *,
        source_video_id: UUID,
        job_id: UUID,
        translations: list[Mapping[str, Any]] | None,
        operator_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        root = self.active_root(source.id)

        def progress(phase: str, percent: int) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        queue_path = root / "phase3_review_queue.json"
        queue = _read_object(queue_path, required=False)
        queue_rows = [
            dict(row)
            for row in list(queue.get("content_objects") or [])
            if isinstance(row, Mapping)
        ]
        if queue_rows:
            supplied = {
                str(row.get("content_id") or ""): str(row.get("vi_text") or "").strip()
                for row in list(translations or [])
                if isinstance(row, Mapping)
            }
            if set(supplied) != {
                str(row.get("content_id") or "") for row in queue_rows
            }:
                raise QualityLocalizationError(
                    "Translation decisions must cover every review object"
                )
            edits = {
                content_id: {"vi_text": value, "reasons": ["frontend_operator_review"]}
                for content_id, value in supplied.items()
            }
            try:
                proposal = build_review_proposal(
                    root_dir=root,
                    edits=edits,
                    proposal_author=operator_id,
                    created_at=_now(),
                )
                proposal_path = root / "phase3_frontend_review_proposal.json"
                _write_json_atomic(proposal_path, proposal)
                apply_review_proposal(
                    root_dir=root,
                    proposal_path=proposal_path,
                    operator_id=operator_id,
                    approved_at=_now(),
                )
            except (Phase3ReviewProposalError, Phase3ProposalApprovalError) as exc:
                raise QualityLocalizationError(
                    f"Translation review validation failed: {exc}"
                ) from exc
            progress("translation_decisions_applied", 15)
            if run_phase3_only.main([str(root)]) != 0:
                raise QualityLocalizationError("Approved Phase 3 rerun failed")
        elif not (root / "phase3_closeout.json").is_file():
            raise QualityLocalizationError("Phase 3 review authority is unavailable")

        if operator_id == AUTO_QUALITY_ACTOR:
            self._prepare_auto_preflight_audio(source.id)
        progress("adaptive_preflight", 30)
        if run_phase4_preflight.main([str(root)]) != 0:
            preflight_meta = _read_object(root / "phase4_preflight_meta.json", required=False)
            preflight_report = _read_object(
                root / "qa" / "phase4_preflight_report.json", required=False
            )
            phase3_handoff = root / "phase3_render_handoff.json"
            current_phase3_sha = (
                _sha256_file(phase3_handoff) if phase3_handoff.is_file() else ""
            )
            if (
                not current_phase3_sha
                or str(preflight_meta.get("phase3_render_handoff_sha256") or "")
                != current_phase3_sha
            ):
                raise QualityLocalizationError(
                    "Adaptive Phase 4 preflight failed before current authority "
                    "was materialized"
                )
            gate = str(preflight_meta.get("final_render_gate") or "").strip()
            status = str(preflight_meta.get("status") or "").strip()
            blocked_reasons = [
                str(value).strip()
                for value in list(preflight_report.get("blocked_reasons") or [])
                if str(value).strip()
            ]
            if gate == "BLOCKED_VISUAL_RESIDUAL_CJK":
                self._set_active_root(source, root, stage="WAITING_RESIDUAL_TRIAGE")
                self.db.commit()
                progress("residual_review_required", 100)
                return self.summary(source.id)
            if status == "PHASE4_PREFLIGHT_BLOCKED" or gate.startswith("BLOCKED_"):
                raise QualityLocalizationError(
                    "Adaptive Phase 4 preflight blocked: "
                    + (
                        ", ".join(blocked_reasons)
                        if blocked_reasons
                        else gate or status or "QUALITY_PREFLIGHT_BLOCKED"
                    )
                )
            raise QualityLocalizationError("Adaptive Phase 4 preflight failed")
        progress("adaptive_visual_preview", 45)
        if self._visual_preview_is_reusable(root):
            # A worker crash after encoded QA but before DB asset persistence
            # must resume at the durable artifact boundary, not render the same
            # 73-second video again.
            progress("adaptive_visual_preview_reused", 90)
        elif self._visual_preview_qa_is_resumable(root):
            # Rendering and muxing are an immutable encoded boundary. If the
            # worker is interrupted during local Output QA, resume QA against
            # the hash-bound video instead of repeating the costly frame pass.
            from scripts.rerun_phase4_output_qa import (
                Phase4OutputQaRerunError,
                rerun_output_qa,
            )

            progress("adaptive_output_qa_resume", 78)
            try:
                resumed_meta = rerun_output_qa(root)
            except Phase4OutputQaRerunError as exc:
                raise QualityLocalizationError(
                    f"Adaptive visual preview QA resume failed: {exc}"
                ) from exc
            if (
                str(resumed_meta.get("status") or "")
                != "VISUAL_PREVIEW_RENDERED"
                or str(resumed_meta.get("output_qa_status") or "") != "PASS"
            ):
                failed_checks = ",".join(
                    str(value)
                    for value in list(
                        resumed_meta.get("output_qa_failed_checks") or []
                    )
                )
                raise QualityLocalizationError(
                    "Adaptive visual preview output QA failed "
                    f"({failed_checks or 'unknown_check'})"
                )
            progress("adaptive_output_qa_complete", 95)
        elif run_phase4_adaptive.main([str(root)]) != 0:
            qa_meta = _read_object(
                root / "phase4_adaptive_render_meta.json", required=False
            )
            failed_checks = ",".join(
                str(value)
                for value in list(qa_meta.get("output_qa_failed_checks") or [])
            )
            raise QualityLocalizationError(
                "Adaptive visual preview output QA failed "
                f"({failed_checks or 'unknown_check'})"
            )
        preview = root / "phase4_adaptive_visual_preview.mp4"
        self._register_workspace_file(
            source,
            preview,
            asset_type=MediaAssetType.CLEANED_VIDEO,
            manifest_group="quality_visual_preview",
            job_id=job_id,
            metadata={
                "workflow_version": QUALITY_WORKFLOW_VERSION,
                "artifact_root": root.relative_to(self.storage.root).as_posix(),
                "visual_preview": True,
                "visual_remediation_sha256": str(
                    dict(
                        _read_object(
                            root / "phase4_visual_remediation_active.json",
                            required=False,
                        ).get("active_ref")
                        or {}
                    ).get("sha256")
                    or ""
                ),
            },
        )
        self._set_active_root(source, root, stage="WAITING_VISUAL_REVIEW")
        self.db.commit()
        progress("completed", 100)
        return self.summary(source.id)

    def run_residual_review(
        self,
        *,
        source_video_id: UUID,
        job_id: UUID,
        action: str,
        suggestions: list[Mapping[str, Any]] | None,
        proposal_sha256: str | None,
        operator_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Suggest, build, or approve a residual-CJK delta.

        Translation suggestions remain non-authoritative. Only the explicit
        proposal approval branch may materialize geometry or resume rendering.
        """

        source = self._source(source_video_id)
        root = self.active_root(source.id)

        def progress(phase: str, percent: int) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        mode = str(action or "")
        proposal_path = root / "phase2_residual_remediation_proposal_frontend.json"
        if mode == "suggest_residual_translation":
            from src.services.quality_auto_policy import translate_residual_texts

            progress("residual_translation_prepare", 5)
            current = self.summary(source.id)
            residual_rows = [
                dict(row)
                for row in list(current.get("residual_review_objects") or [])
                if isinstance(row, Mapping)
            ]
            authority_sha256 = str(
                current.get("residual_authority_sha256") or ""
            ).strip()
            if not residual_rows or not authority_sha256:
                raise QualityLocalizationError(
                    "Residual translation requires current residual OCR authority"
                )
            input_sha256 = _residual_translation_input_sha256(
                residual_rows,
                authority_sha256=authority_sha256,
            )
            owner_job = self.db.get(Job, job_id)
            owner_payload = dict(owner_job.payload_json or {}) if owner_job else {}
            expected_authority = str(
                owner_payload.get("residual_authority_sha256") or ""
            ).strip()
            expected_input = str(
                owner_payload.get("residual_translation_input_sha256") or ""
            ).strip()
            if expected_authority and expected_authority != authority_sha256:
                raise QualityLocalizationError(
                    "Residual OCR authority changed after translation was queued"
                )
            if expected_input and expected_input != input_sha256:
                raise QualityLocalizationError(
                    "Residual translation input changed after translation was queued"
                )

            suggestion_path = root / "phase2_residual_translation_suggestions.json"
            cached = _read_object(suggestion_path, required=False)
            cached_rows = [
                dict(row)
                for row in list(cached.get("suggestions") or [])
                if isinstance(row, Mapping)
            ]
            expected_texts = {
                str(row.get("text") or "").strip()
                for row in residual_rows
                if str(row.get("text") or "").strip()
            }
            cached_by_text = {
                str(row.get("ocr_text") or "").strip(): row
                for row in cached_rows
                if str(row.get("ocr_text") or "").strip()
            }
            cache_current = bool(
                str(cached.get("status") or "") == "SUGGESTION_ONLY"
                and not bool(cached.get("operator_approval_written"))
                and str(cached.get("residual_authority_sha256") or "")
                == authority_sha256
                and str(cached.get("input_sha256") or "") == input_sha256
                and expected_texts
                and expected_texts.issubset(cached_by_text)
                and all(
                    str(cached_by_text[text].get("ocr_text_corrected") or "").strip()
                    and str(cached_by_text[text].get("vi_text_suggested") or "").strip()
                    for text in expected_texts
                )
            )
            if cache_current:
                progress("residual_translation_cache_hit", 90)
            else:
                progress("residual_translation_provider", 25)
                phase3_authority = _read_object(
                    root / "phase3_translation_timeline.json", required=False
                )
                authority_suggestions = translation_authority_suggestions(
                    residual_rows,
                    [
                        dict(row)
                        for row in list(phase3_authority.get("content_objects") or [])
                        if isinstance(row, Mapping)
                    ],
                )
                try:
                    cached_rows = translate_residual_texts(
                        db=self.db,
                        workspace_id=source.workspace_id,
                        residual_objects=residual_rows,
                        fallback_suggestions=cached_rows,
                        authority_suggestions=authority_suggestions,
                        cache_path=root / "phase2_residual_translation_cache.json",
                        on_progress=(
                            lambda completed, total: progress(
                                f"residual_translation_provider|{completed}|{total}",
                                25
                                + int(
                                    60.0
                                    * max(0, completed)
                                    / max(1, total)
                                ),
                            )
                        ),
                    )
                except QualityAutoPolicyBlocked as exc:
                    raise QualityLocalizationError(str(exc)) from exc
                _write_json_atomic(
                    suggestion_path,
                    {
                        "schema_version": "phase2_residual_translation_suggestions_v2",
                        "status": "SUGGESTION_ONLY",
                        "operator_approval_written": False,
                        "created_at": _now(),
                        "residual_authority_sha256": authority_sha256,
                        "input_sha256": input_sha256,
                        "suggestions": [dict(row) for row in cached_rows],
                    },
                )
            # Suggestion generation never changes the operator checkpoint.
            self._set_active_root(source, root, stage="WAITING_RESIDUAL_TRIAGE")
            self.db.commit()
            progress("completed", 100)
            return self.summary(source.id)

        if mode == "auto_residual_remediation":
            from src.services.quality_auto_policy import translate_residual_texts

            def encoded_output_residual_pending() -> bool:
                qa = _read_object(
                    root / "qa" / "phase4_adaptive_visual_preview_output_qa.json",
                    required=False,
                )
                rendered = _read_object(
                    root / "phase4_adaptive_render_meta.json", required=False
                )
                residual = dict(qa.get("residual_cjk") or {})
                video_name = str(dict(rendered.get("artifacts") or {}).get("video") or "")
                video_path = (root / video_name).resolve()
                return bool(
                    str(rendered.get("status") or "")
                    == "VISUAL_PREVIEW_QA_FAILED"
                    and str(rendered.get("output_qa_status") or "") == "FAIL"
                    and "residual_cjk"
                    in list(rendered.get("output_qa_failed_checks") or [])
                    and str(qa.get("status") or "") == "FAIL"
                    and "residual_cjk" in list(qa.get("failed_checks") or [])
                    and bool(residual.get("complete"))
                    and bool(list(residual.get("detections") or []))
                    and video_name
                    and video_path.is_relative_to(root)
                    and video_path.is_file()
                    and str(rendered.get("phase4_input_sha256") or "")
                    == _sha256_file(root / "phase4_render_input.json")
                    and str(rendered.get("output_video_sha256") or "")
                    == _sha256_file(video_path)
                )

            encoded_residual_pending = encoded_output_residual_pending()

            # A previous worker may have materialized the additive remediation and
            # crashed before the Phase 3 handoff was regenerated. Rebind/rebuild the
            # approved carry-forward first so this auto job is genuinely resumable.
            active_pointer = root / "phase2_residual_remediation_active.json"
            if active_pointer.is_file() and encoded_residual_pending:
                from src.services.residual_remediation_authority import (
                    resolve_active_residual_remediation,
                )

                active_remediation = resolve_active_residual_remediation(root)
                active_payload = (
                    _read_object(active_remediation, required=False)
                    if active_remediation is not None
                    else {}
                )
                qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
                qa_ref = dict(
                    dict(active_payload.get("authority_refs") or {}).get(
                        "phase4_output_qa"
                    )
                    or {}
                )
                if (
                    active_remediation is not None
                    and qa_path.is_file()
                    and str(qa_ref.get("sha256") or "") == _sha256_file(qa_path)
                ):
                    # The exact encoded residual delta was already materialized
                    # before a worker retry. Resume at the first stale downstream
                    # boundary instead of creating the same occurrence ids again.
                    phase2 = _read_object(root / "phase2_handoff.json", required=False)
                    phase2_ref = dict(phase2.get("residual_remediation_ref") or {})
                    active_file_sha = _sha256_file(active_remediation)
                    phase2_current = (
                        str(phase2.get("status") or "") == "READY_FOR_PHASE3"
                        and str(phase2_ref.get("path") or "") == active_remediation.name
                        and str(phase2_ref.get("sha256") or "") == active_file_sha
                    )
                    if not phase2_current:
                        progress("auto_residual_resume_phase2", 25)
                        if self._run_phase2_with_semantic_authority(
                            source=source,
                            root=root,
                            video_path=self._source_video_path(source.id),
                        ) != 0:
                            raise QualityLocalizationError(
                                "Residual Phase 2 resume rerun failed"
                            )
                    _require_phase2_ready_for_phase3(
                        root,
                        operation="Residual Phase 2 resume rerun",
                    )
                    progress("auto_residual_resume_phase3", 45)
                    try:
                        stage_unapproved_placeholders(root)
                        if run_phase3_only.main([str(root)]) != 0:
                            raise QualityLocalizationError(
                                "Residual Phase 3 resume staging failed"
                            )
                        rebind_phase3_approvals(root)
                    except Phase3ApprovalRebindError as exc:
                        raise QualityLocalizationError(str(exc)) from exc
                    if run_phase3_only.main([str(root)]) != 0:
                        raise QualityLocalizationError(
                            "Residual Phase 3 resume approval rerun failed"
                        )
                    progress("auto_residual_resume_phase4", 60)
                    return self.run_translation_and_preview(
                        source_video_id=source.id,
                        job_id=job_id,
                        translations=None,
                        operator_id=operator_id,
                        on_progress=(
                            lambda phase, percent: progress(
                                phase,
                                60
                                + int(max(0, min(100, int(percent or 0))) * 0.4),
                            )
                        ),
                    )
            # An active remediation pointer is normally a resumable Phase 3/4
            # handoff.  It must not mask a *new* residual discovered only after
            # encoded Output QA; that evidence requires an additive delta.
            if active_pointer.is_file() and not encoded_residual_pending:
                phase2_path = root / "phase2_handoff.json"
                phase3_path = root / "phase3_render_handoff.json"
                phase3_payload = _read_object(phase3_path, required=False)
                phase3_current = (
                    phase2_path.is_file()
                    and phase3_path.is_file()
                    and str(
                        dict(phase3_payload.get("phase2_handoff_ref") or {}).get(
                            "sha256"
                        )
                        or ""
                    )
                    == _sha256_file(phase2_path)
                    and str(phase3_payload.get("status") or "")
                    == "READY_FOR_RENDER"
                )
                if not phase3_current:
                    try:
                        _require_phase2_ready_for_phase3(
                            root,
                            operation="Phase 2 residual recovery",
                        )
                        stage_unapproved_placeholders(root)
                        if run_phase3_only.main([str(root)]) != 0:
                            raise QualityLocalizationError(
                                "Phase 3 recovery rerun failed"
                            )
                        rebind_phase3_approvals(root)
                        if run_phase3_only.main([str(root)]) != 0:
                            raise QualityLocalizationError(
                                "Phase 3 approval recovery rerun failed"
                            )
                    except Phase3ApprovalRebindError as exc:
                        raise QualityLocalizationError(str(exc)) from exc

                # A prior attempt may already have materialized a valid remediation.
                # Do not run a new preflight/proposal against the masked timeline (it
                # correctly reports zero residuals and loses the original authority).
                from src.services.residual_remediation_authority import (
                    resolve_active_residual_remediation,
                )

                active_remediation = resolve_active_residual_remediation(root)
                if active_remediation is not None:
                    progress("auto_residual_resume", 35)
                    return self.run_translation_and_preview(
                        source_video_id=source.id,
                        job_id=job_id,
                        translations=None,
                        operator_id=operator_id,
                        on_progress=(
                            lambda phase, percent: progress(
                                phase,
                                35 + int(max(0, min(100, int(percent or 0))) * 0.65),
                            )
                        ),
                    )

            # Phase 4 evidence is bound to the Phase 3 handoff. Refresh it after any
            # recovery; a residual block is expected here and feeds the proposal
            # builder, while unrelated preflight failures remain terminal.
            preflight_exit = run_phase4_preflight.main([str(root)])
            if preflight_exit != 0:
                refreshed = _read_object(
                    root / "phase4_preflight_meta.json", required=False
                )
                if str(refreshed.get("final_render_gate") or "") != (
                    "BLOCKED_VISUAL_RESIDUAL_CJK"
                ):
                    raise QualityLocalizationError(
                        "Residual auto-remediation preflight refresh failed"
                    )
            preflight = _read_object(root / "phase4_preflight_meta.json")
            if encoded_output_residual_pending():
                output_qa = _read_object(
                    root / "qa" / "phase4_adaptive_visual_preview_output_qa.json",
                    required=False,
                )
                residual_evidence = dict(output_qa.get("residual_cjk") or {})
            else:
                residual_evidence = dict(preflight.get("residual_cjk") or {})
            residual_rows = [
                {
                    **dict(row),
                    "content_id": f"residual_{index + 1:03d}",
                }
                for index, row in enumerate(
                    list(residual_evidence.get("detections") or [])
                )
                if isinstance(row, Mapping)
            ]
            if not residual_rows:
                raise QualityLocalizationError(
                    "Residual auto-remediation has no current encoded/preflight detections"
                )
            try:
                cached_suggestions = list(
                    _read_object(
                        root / "phase2_residual_translation_suggestions.json",
                        required=False,
                    ).get("suggestions")
                    or []
                )
                suggestions = translate_residual_texts(
                    db=self.db,
                    workspace_id=source.workspace_id,
                    residual_objects=residual_rows,
                    fallback_suggestions=cached_suggestions,
                    authority_suggestions=translation_authority_suggestions(
                        residual_rows,
                        [
                            dict(row)
                            for row in list(
                                _read_object(
                                    root / "phase3_translation_timeline.json",
                                    required=False,
                                ).get("content_objects")
                                or []
                            )
                            if isinstance(row, Mapping)
                        ],
                    ),
                    cache_path=root / "phase2_residual_translation_cache.json",
                    on_progress=(
                        lambda completed, total: progress(
                            f"residual_translation_provider|{completed}|{total}",
                            5
                            + int(15.0 * max(0, completed) / max(1, total)),
                        )
                    ),
                )
            except QualityAutoPolicyBlocked as exc:
                raise QualityLocalizationError(str(exc)) from exc
            suggestion_authority_sha256 = (
                _sha256_file(
                    root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
                )
                if encoded_output_residual_pending()
                else _sha256_file(root / "phase4_preflight_meta.json")
            )
            suggestion_payload = {
                "schema_version": "phase2_residual_translation_suggestions_v1",
                "status": "SUGGESTION_ONLY",
                "operator_approval_written": False,
                "created_at": _now(),
                "residual_authority_sha256": suggestion_authority_sha256,
                "input_sha256": _residual_translation_input_sha256(
                    residual_rows,
                    authority_sha256=suggestion_authority_sha256,
                ),
                "suggestions": [dict(row) for row in suggestions],
            }
            _write_json_atomic(
                root / "phase2_residual_translation_suggestions.json",
                suggestion_payload,
            )
            progress("auto_residual_proposal", 20)
            try:
                proposal = build_residual_remediation_proposal(root)
                validate_residual_remediation_proposal(root, proposal)
            except ResidualRemediationProposalError as exc:
                raise QualityLocalizationError(str(exc)) from exc
            _write_json_atomic(proposal_path, proposal)
            proposal_sha256 = str(proposal.get("proposal_sha256") or "")
            operator_id = AUTO_QUALITY_ACTOR
            mode = "approve_residual_proposal"
        if mode == "build_residual_proposal":
            current = self.summary(source.id)
            current_rows = [
                dict(row)
                for row in list(current.get("residual_review_objects") or [])
                if isinstance(row, Mapping)
            ]
            current_authority = str(
                current.get("residual_authority_sha256") or ""
            ).strip()
            suggestion_payload = {
                "schema_version": "phase2_residual_translation_suggestions_v1",
                "status": "SUGGESTION_ONLY",
                "operator_approval_written": False,
                "created_at": _now(),
                "residual_authority_sha256": current_authority or None,
                "input_sha256": (
                    _residual_translation_input_sha256(
                        current_rows,
                        authority_sha256=current_authority,
                    )
                    if current_rows and current_authority
                    else None
                ),
                "suggestions": [dict(row) for row in list(suggestions or [])],
            }
            _write_json_atomic(
                root / "phase2_residual_translation_suggestions.json",
                suggestion_payload,
            )
            progress("residual_proposal", 20)
            try:
                proposal = build_residual_remediation_proposal(root)
                validate_residual_remediation_proposal(root, proposal)
            except ResidualRemediationProposalError as exc:
                raise QualityLocalizationError(str(exc)) from exc
            _write_json_atomic(proposal_path, proposal)
            self._set_active_root(source, root, stage="WAITING_RESIDUAL_REVIEW")
            self.db.commit()
            progress("completed", 100)
            return self.summary(source.id)

        if mode != "approve_residual_proposal":
            raise QualityLocalizationError(f"Unsupported residual action: {mode}")
        progress("residual_materialize", 10)
        active_remediation = _matching_active_residual_remediation(
            root,
            proposal_sha256=str(proposal_sha256 or ""),
        )
        if active_remediation is None:
            if not proposal_path.is_file():
                raise QualityLocalizationError(
                    "Residual remediation proposal is missing"
                )
            try:
                delta = materialize_remediation(
                    root_dir=root,
                    proposal_path=proposal_path,
                    approved_proposal_sha256=str(proposal_sha256 or ""),
                    operator_id=operator_id,
                    approved_at=_now(),
                )
                activate_cumulative_remediation(root_dir=root, delta=delta)
            except ResidualRemediationMaterializationError as exc:
                raise QualityLocalizationError(str(exc)) from exc
        else:
            progress("residual_resume_active", 15)
        progress("phase2_delta", 25)
        if self._run_phase2_with_semantic_authority(
            source=source,
            root=root,
            video_path=self._source_video_path(source.id),
        ) != 0:
            raise QualityLocalizationError("Residual Phase 2 rerun failed")
        _require_phase2_ready_for_phase3(
            root,
            operation="Residual Phase 2 rerun",
        )
        progress("phase3_rebind", 45)
        try:
            stage_unapproved_placeholders(root)
            if run_phase3_only.main([str(root)]) != 0:
                raise QualityLocalizationError("Residual Phase 3 staging failed")
            rebind_phase3_approvals(root)
        except Phase3ApprovalRebindError as exc:
            raise QualityLocalizationError(str(exc)) from exc
        if run_phase3_only.main([str(root)]) != 0:
            raise QualityLocalizationError("Residual Phase 3 approval rerun failed")
        progress("phase4_resume", 60)
        return self.run_translation_and_preview(
            source_video_id=source.id,
            job_id=job_id,
            translations=None,
            operator_id=operator_id,
            on_progress=(
                lambda phase, percent: progress(
                    phase, 60 + int(max(0, min(100, int(percent or 0))) * 0.4)
                )
            ),
        )

    def _visual_preview_is_reusable(self, root: Path) -> bool:
        """Return true only for a hash-bound, current-policy PASS artifact."""
        meta = _read_object(root / "phase4_adaptive_render_meta.json", required=False)
        if (
            str(meta.get("status") or "") != "VISUAL_PREVIEW_RENDERED"
            or str(meta.get("output_qa_status") or "") != "PASS"
        ):
            return False
        output_name = str(dict(meta.get("artifacts") or {}).get("video") or "")
        output = (root / output_name).resolve()
        if (
            not output_name
            or not output.is_relative_to(root)
            or not output.is_file()
            or _sha256_file(output) != str(meta.get("output_video_sha256") or "")
        ):
            return False
        input_path = root / "phase4_render_input.json"
        if _sha256_file(input_path) != str(meta.get("phase4_input_sha256") or ""):
            return False
        active_ref = dict(
            _read_object(root / "phase4_visual_remediation_active.json", required=False).get(
                "active_ref"
            )
            or {}
        )
        if active_ref != dict(meta.get("visual_remediation_ref") or {}):
            return False
        qa_name = str(dict(meta.get("artifacts") or {}).get("output_qa") or "")
        qa_path = (root / qa_name).resolve()
        if not qa_name or not qa_path.is_relative_to(root):
            return False
        qa = _read_object(qa_path, required=False)
        residual = dict(qa.get("residual_cjk") or {})
        return (
            str(qa.get("status") or "") == "PASS"
            and str(residual.get("policy_version") or "")
            == "source_intrinsic_cjk_v12_temporal_provenance"
            and not list(residual.get("detections") or [])
        )

    def _visual_preview_qa_is_resumable(self, root: Path) -> bool:
        """Verify an encoded preview whose only unfinished boundary is QA."""

        meta = _read_object(
            root / "phase4_adaptive_render_meta.json", required=False
        )
        if (
            str(meta.get("status") or "")
            != "VISUAL_PREVIEW_OUTPUT_QA_PENDING"
            or str(meta.get("output_qa_status") or "") != "PENDING"
            or not bool(meta.get("visual_preview"))
        ):
            return False
        input_path = root / "phase4_render_input.json"
        if (
            not input_path.is_file()
            or _sha256_file(input_path)
            != str(meta.get("phase4_input_sha256") or "")
        ):
            return False
        output_name = str(dict(meta.get("artifacts") or {}).get("video") or "")
        output = (root / output_name).resolve()
        if (
            not output_name
            or not output.is_relative_to(root)
            or not output.is_file()
            or _sha256_file(output)
            != str(meta.get("output_video_sha256") or "")
        ):
            return False
        active_ref = dict(
            _read_object(
                root / "phase4_visual_remediation_active.json", required=False
            ).get("active_ref")
            or {}
        )
        return active_ref == dict(meta.get("visual_remediation_ref") or {})

    def _build_phase1_candidate_seed(
        self,
        *,
        source: SourceVideo,
        root_hint: Path,
        job_id: UUID,
    ) -> tuple[Path, dict[str, Any]]:
        """Build local audio-guided windows from persisted transcript timing.

        This method never invokes VAD, ASR, OCR or a network provider. A
        verified no-dialogue source may use Visual-Only mode. If persisted VAD
        says speech exists, missing usable transcript timing is an upstream
        authority error and must fail closed instead of silently slowing OCR.
        """

        rows = list(
            self.db.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.source_video_id == source.id,
                    TranscriptSegment.is_current.is_(True),
                )
                .order_by(
                    TranscriptSegment.segment_index.asc(),
                    TranscriptSegment.version.desc(),
                )
            ).all()
        )
        # Defensive de-duplication protects older databases where two current
        # versions survived an interrupted transcript edit.
        segments: list[dict[str, Any]] = []
        seen_indices: set[int] = set()
        rejected_segments = 0
        invalid_segments = 0
        for row in rows:
            index = int(row.segment_index)
            if index in seen_indices:
                continue
            seen_indices.add(index)
            status = getattr(row.status, "value", str(row.status)).upper()
            text = str(row.text or "").strip()
            start_ms = int(row.start_ms)
            end_ms = int(row.end_ms)
            if status == TranscriptSegmentStatus.REJECTED.value:
                rejected_segments += 1
                continue
            if not text or start_ms < 0 or end_ms <= start_ms:
                invalid_segments += 1
                continue
            segments.append(
                {
                    "segment_index": index,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "confidence": float(row.confidence or 0.0),
                    "status": status,
                    "analysis_version": str(row.analysis_version or ""),
                    "text_sha256": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                }
            )
        source_metadata = dict(source.metadata_json or {})
        vad_metadata = dict(source_metadata.get("vad") or {})
        vad_has_speech = vad_metadata.get("has_speech")
        if vad_has_speech is None:
            vad_has_speech = source_metadata.get("has_speech")
        if vad_has_speech is not None:
            vad_has_speech = bool(vad_has_speech)
        audio_cache = dict(source_metadata.get("audio_analysis_cache") or {})
        audio_analysis_version = str(
            audio_cache.get("analysis_version")
            or next(
                (
                    row["analysis_version"]
                    for row in segments
                    if row.get("analysis_version")
                ),
                "",
            )
        )
        audio_analysis_fingerprint = str(audio_cache.get("fingerprint") or "")
        duration_ms = max(
            int(round(float(source.duration_seconds or 0.0) * 1000.0)),
            max((int(row["end_ms"]) for row in segments), default=0),
            1,
        )
        windows = build_audio_candidate_windows(
            segments,
            duration_ms=duration_ms,
        )
        if vad_has_speech is True and not windows:
            raise QualityLocalizationError(
                "Analyze OCR requires usable current transcript timing because "
                "Analyze Audio detected speech; re-run Analyze Audio before OCR"
            )
        transcript_authority = {
            "source_video_id": str(source.id),
            "vad_has_speech": vad_has_speech,
            "audio_analysis_version": audio_analysis_version,
            "audio_analysis_fingerprint": audio_analysis_fingerprint,
            "segments": segments,
        }
        transcript_sha256 = _sha256_json(transcript_authority)
        payload: dict[str, Any] = {
            "schema_version": "phase1_candidate_seed_v1",
            "engine_version": QUALITY_ANALYSIS_ENGINE,
            "source_video_id": str(source.id),
            "duration_ms": duration_ms,
            "mode": "AUDIO_GUIDED_VISUAL" if windows else "VISUAL_ONLY",
            "vad_has_speech": vad_has_speech,
            "audio_analysis_version": audio_analysis_version,
            "audio_analysis_fingerprint": audio_analysis_fingerprint,
            "source_transcript_sha256": transcript_sha256,
            "segments_count": len(segments),
            "rejected_segments_count": rejected_segments,
            "invalid_segments_count": invalid_segments,
            "windows": [row.to_dict() for row in windows],
            "network_calls": 0,
        }
        payload["seed_sha256"] = _sha256_json(payload)
        seed_dir = root_hint / ".phase1_candidate_seeds"
        seed_dir.mkdir(parents=True, exist_ok=True)
        seed_path = seed_dir / f"{source.id}_{job_id}.json"
        _write_json_atomic(seed_path, payload)
        return seed_path, payload

    def _run_phase1_subprocess(
        self,
        *,
        video_path: Path,
        root: Path,
        on_progress: Callable[[str, int, int], None],
        analysis_engine: str,
        candidate_windows_path: Path,
    ) -> int:
        """Run DBNet outside the worker process with progress and a no-progress watchdog."""

        settings = get_settings()
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        command = [
            sys.executable,
            "-m",
            "scripts.run_phase1_only",
            str(video_path),
            str(root),
            "--step",
            "1",
            "--engine",
            str(analysis_engine),
            "--candidate-windows",
            str(candidate_windows_path),
        ]
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            assert process.stdout is not None
            for raw in process.stdout:
                lines.put(raw.rstrip("\r\n"))
            lines.put(None)

        reader = threading.Thread(target=_reader, name="phase1-progress-reader", daemon=True)
        reader.start()
        last_progress = time.monotonic()
        last_phase = "phase1_startup"
        try:
            while True:
                try:
                    line = lines.get(timeout=1.0)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line.startswith("[P1_PROGRESS] "):
                    parts = line.split()
                    if len(parts) == 4:
                        try:
                            on_progress(parts[1], int(parts[2]), int(parts[3]))
                            last_progress = time.monotonic()
                            last_phase = parts[1]
                        except ValueError:
                            pass
                if process.poll() is not None and lines.empty():
                    break
                timeout_seconds = _phase1_watchdog_timeout_seconds(
                    settings, last_phase
                )
                if time.monotonic() - last_progress > timeout_seconds:
                    raise QualityLocalizationError(
                        "Phase 1 emitted no progress for "
                        f"{timeout_seconds}s during {last_phase}"
                    )
            return int(process.wait(timeout=10))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            reader.join(timeout=2)

    def approve_visual(
        self, source_video_id: UUID, *, operator_id: str
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        root = self.active_root(source.id)
        record_visual_approval(
            root_dir=root,
            video_path=root / "phase4_adaptive_visual_preview.mp4",
            output_qa_path=(
                root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
            ),
            operator_id=operator_id,
        )
        self._set_active_root(source, root, stage="VISUAL_APPROVED")
        self.db.commit()
        return self.stage_audio_review(source.id, operator_id=operator_id)

    def _prepare_auto_preflight_audio(self, source_video_id: UUID) -> None:
        """Stage hash-verified audio before an unattended visual preflight.

        Phase 4 preflight requires audio authority, while the interactive flow
        normally creates it after visual approval. Full auto has no operator between
        those steps, so it binds the already approved TTS/background artifacts first;
        the later mix preview and QA still run normally.
        """

        from src.audio_pipeline.services.background_recovery_service import (
            BackgroundRecoveryError,
            BackgroundRecoveryService,
        )
        from src.tts_pipeline.services.tts_service import TtsPipelineService

        source = self._source(source_video_id)
        root = self.active_root(source.id)
        narration = self._current_asset(source.id, MediaAssetType.TTS_AUDIO_JOINED)
        if narration is None:
            metadata = dict(source.metadata_json or {})
            vad_metadata = dict(dict(metadata.get("vad") or {}).get("metadata") or {})
            if not isinstance(metadata.get("audio_input"), Mapping):
                metadata["audio_input"] = {
                    "source_video_duration_seconds": float(
                        metadata.get("duration_seconds")
                        or vad_metadata.get("duration_seconds")
                        or vad_metadata.get("audio_seconds")
                        or 0.0
                    )
                }
            token = f"AUDIO_APPROVED_NO_DIALOGUE_{str(source.id).upper()}"
            try:
                stage_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    source_video_path=self._source_video_path(source.id),
                    analysis_metadata=metadata,
                    source_video_id=str(source.id),
                    required_approval_token=token,
                )
                approve_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    approval_token=token,
                    operator_id=AUTO_QUALITY_ACTOR,
                )
            except Phase4ApprovalError as exc:
                raise QualityLocalizationError(str(exc)) from exc
            return

        narration_path = self.storage.resolve(narration.storage_key).absolute_path
        background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None:
            try:
                BackgroundRecoveryService(self.db, storage=self.storage).recover(source.id)
            except BackgroundRecoveryError as exc:
                raise QualityLocalizationError(str(exc)) from exc
            background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None:
            raise QualityLocalizationError(
                "Original background stem is required for auto preflight"
            )
        background_path = self.storage.resolve(background.storage_key).absolute_path
        manifest = TtsPipelineService(self.db).get_render_prep_manifest(source.id)
        try:
            prepare_approved_audio_handoff(
                root_dir=root,
                manifest=manifest,
                narration_path=narration_path,
                background_path=background_path,
                operator_id=AUTO_QUALITY_ACTOR,
            )
        except Phase4ApprovalError as exc:
            raise QualityLocalizationError(str(exc)) from exc

    def stage_audio_review(
        self, source_video_id: UUID, *, operator_id: str
    ) -> dict[str, Any]:
        """Build a listenable narration+music preview without approving the mix."""

        from src.audio_pipeline.services.background_recovery_service import (
            BackgroundRecoveryError,
            BackgroundRecoveryService,
        )
        from src.tts_pipeline.services.tts_service import TtsPipelineService

        source = self._source(source_video_id)
        root = self.active_root(source.id)
        if not (root / "phase4_visual_approval.json").is_file():
            raise QualityLocalizationError("Adaptive visual preview is not approved")
        narration = self._current_asset(source.id, MediaAssetType.TTS_AUDIO_JOINED)
        if narration is None:
            analysis_metadata = dict(source.metadata_json or {})
            if not isinstance(analysis_metadata.get("audio_input"), Mapping):
                vad_metadata = dict(
                    dict(analysis_metadata.get("vad") or {}).get("metadata") or {}
                )
                analysis_metadata["audio_input"] = {
                    "source_video_duration_seconds": float(
                        analysis_metadata.get("duration_seconds")
                        or vad_metadata.get("duration_seconds")
                        or vad_metadata.get("audio_seconds")
                        or 0.0
                    )
                }
            try:
                stage_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    source_video_path=self._source_video_path(source.id),
                    analysis_metadata=analysis_metadata,
                    source_video_id=str(source.id),
                    required_approval_token=(
                        f"AUDIO_APPROVED_NO_DIALOGUE_{str(source.id).upper()}"
                    ),
                )
            except Phase4ApprovalError as exc:
                raise QualityLocalizationError(
                    "Joined Vietnamese narration is missing and the source has no "
                    f"verified no-dialogue authority: {exc}"
                ) from exc
            self._set_active_root(source, root, stage="WAITING_AUDIO_REVIEW")
            self.db.commit()
            return self.summary(source.id)
        narration_path = self.storage.resolve(narration.storage_key).absolute_path
        background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None:
            try:
                BackgroundRecoveryService(self.db, storage=self.storage).recover(source.id)
            except BackgroundRecoveryError as exc:
                raise QualityLocalizationError(
                    f"Original background stem could not be recovered: {exc}"
                ) from exc
            background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None:
            raise QualityLocalizationError(
                "Original background stem is required for audio-mix review"
            )
        background_path = self.storage.resolve(background.storage_key).absolute_path
        manifest = _read_object(root / "render_prep_manifest.json", required=False)
        if not manifest:
            manifest = TtsPipelineService(self.db).get_render_prep_manifest(source.id)
        self._assert_tts_manifest_authority(source, manifest)
        try:
            prepare_approved_audio_handoff(
                root_dir=root,
                manifest=manifest,
                narration_path=narration_path,
                background_path=background_path,
                operator_id=operator_id,
            )
            approved_manifest = _read_object(root / "render_prep_manifest.json")
            stage_background_mix_review(
                root_dir=root,
                manifest=approved_manifest,
                narration_path=root / "phase4_joined_narration.wav",
                background_path=root / "phase4_background.wav",
            )
        except Phase4ApprovalError as exc:
            raise QualityLocalizationError(str(exc)) from exc
        self._set_active_root(source, root, stage="WAITING_AUDIO_REVIEW")
        self.db.commit()
        return self.summary(source.id)

    def approve_audio_review(
        self, source_video_id: UUID, *, operator_id: str
    ) -> dict[str, Any]:
        """Approve exactly the hash-bound mix preview the operator listened to."""

        source = self._source(source_video_id)
        root = self.active_root(source.id)
        try:
            no_dialogue_review = _read_object(
                root / "phase4_no_dialogue_audio_review.json", required=False
            )
            if str(no_dialogue_review.get("status") or "") == "PENDING_AUDIO_REVIEW":
                approve_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    approval_token=str(
                        no_dialogue_review.get("required_approval_token") or ""
                    ),
                    operator_id=operator_id,
                )
            else:
                approve_background_mix_review(
                    root_dir=root,
                    approval_token="AUDIO_MIX_APPROVED",
                    operator_id=operator_id,
                )
        except Phase4ApprovalError as exc:
            raise QualityLocalizationError(str(exc)) from exc
        self._set_active_root(source, root, stage="AUDIO_APPROVED")
        self.db.commit()
        return self.summary(source.id)

    def prepare_final_audio(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
    ) -> Path:
        from src.tts_pipeline.services.tts_service import TtsPipelineService
        from src.audio_pipeline.services.background_recovery_service import (
            BackgroundRecoveryError,
            BackgroundRecoveryService,
        )

        source = self._source(source_video_id)
        root = self.active_root(source.id)
        if not (root / "phase4_visual_approval.json").is_file():
            raise QualityLocalizationError("Adaptive visual preview is not approved")
        mix_approval = _read_object(
            root / "phase4_background_mix_approval.json", required=False
        )
        audio_approval = _read_object(
            root / "phase4_audio_approval.json", required=False
        )
        audio_is_approved = (
            str(mix_approval.get("status") or "") == "AUDIO_MIX_APPROVED"
            or str(audio_approval.get("status") or "") == "AUDIO_APPROVED"
        )
        if not audio_is_approved:
            raise QualityLocalizationError(
                "Audio mix requires explicit operator approval before final render"
            )
        manifest = _read_object(root / "render_prep_manifest.json", required=False)
        if not manifest:
            manifest = TtsPipelineService(self.db).get_render_prep_manifest(source.id)
        self._assert_tts_manifest_authority(source, manifest)
        narration = self._current_asset(source.id, MediaAssetType.TTS_AUDIO_JOINED)
        narration_path: Path | None = None
        verified_no_dialogue_source_audio = False
        if narration is not None:
            narration_path = self.storage.resolve(narration.storage_key).absolute_path
        else:
            # A verified NO_DIALOGUE case intentionally has no TTS asset.  The
            # Phase 4 authority stages the source audio in the persistent run
            # root and records it as joined_narration with a distinct role.
            joined = list(dict(manifest.get("current_outputs") or {}).get("joined_narration") or [])
            if len(joined) == 1 and str(dict(joined[0]).get("role") or "") == "verified_no_dialogue_source_audio":
                candidate = (root / str(dict(joined[0]).get("storage_key") or "")).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    narration_path = candidate
                    verified_no_dialogue_source_audio = True
            if narration_path is None:
                raise QualityLocalizationError(
                    "Joined Vietnamese narration is missing and no approved no-dialogue source-audio handoff is available"
                )
        background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None and not verified_no_dialogue_source_audio:
            # Audio analysis already produced Demucs files for this source, but
            # older runs did not persist the stem rows. Recovering here keeps
            # the frontend's single Start Render action lossless and avoids
            # silently replacing the original music with narration-only audio.
            try:
                BackgroundRecoveryService(self.db, storage=self.storage).recover(source.id)
            except BackgroundRecoveryError as exc:
                raise QualityLocalizationError(
                    f"Original background stem could not be recovered: {exc}"
                ) from exc
            background = self._current_asset(source.id, MediaAssetType.AUDIO_BACKGROUND_STEM)
        if background is None and not verified_no_dialogue_source_audio:
            raise QualityLocalizationError(
                "Original background stem is required for this dialogue video"
            )
        background_path = (
            self.storage.resolve(background.storage_key).absolute_path
            if background is not None
            else None
        )
        try:
            manifest_outputs = dict(manifest.get("current_outputs") or {})
            if verified_no_dialogue_source_audio:
                prepare_approved_audio_handoff(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=narration_path,
                    background_path=None,
                    operator_id=operator_id,
                )
            elif not list(manifest_outputs.get("background_audio") or []):
                attach_background_and_approve(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=narration_path,
                    background_path=background_path,
                    operator_id=operator_id,
                )
            else:
                # The DB manifest may already reference the Demucs stem while
                # this quality run has never staged its local authority files.
                # Materialize both audio inputs into the active root before the
                # mix-review code reads render_prep_manifest.json.
                prepare_approved_audio_handoff(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=narration_path,
                    background_path=background_path,
                    operator_id=operator_id,
                )
            manifest = _read_object(root / "render_prep_manifest.json")
            mix_approval = _read_object(
                root / "phase4_background_mix_approval.json", required=False
            )
            if (
                not verified_no_dialogue_source_audio
                and str(mix_approval.get("status") or "") != "AUDIO_MIX_APPROVED"
            ):
                from src.media_pipeline.video_renderer.phase4_approvals import (
                    approve_background_mix_review,
                    stage_background_mix_review,
                )

                stage_background_mix_review(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=root / "phase4_joined_narration.wav",
                    background_path=background_path,
                )
                approve_background_mix_review(
                    root_dir=root,
                    approval_token="AUDIO_MIX_APPROVED",
                    operator_id=operator_id,
                )
        except Phase4ApprovalError as exc:
            raise QualityLocalizationError(str(exc)) from exc
        if run_phase4_preflight.main([str(root)]) != 0:
            raise QualityLocalizationError("Final adaptive preflight failed")
        try:
            from scripts.rebind_phase4_audio_authority import (
                Phase4AudioRebindError,
                rebind,
            )

            rebind(root, operator_id=operator_id)
        except Phase4AudioRebindError as exc:
            raise QualityLocalizationError(
                f"Final audio authority rebind failed: {exc}"
            ) from exc
        return root

    def run_final_adaptive(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        try:
            root_for_authority = self.active_root(source_video_id)
        except QualityLocalizationError:
            root_for_authority = None
        if root_for_authority is not None:
            manifest_for_authority = _read_object(
                root_for_authority / "render_prep_manifest.json",
                required=False,
            )
            if manifest_for_authority:
                self._assert_tts_manifest_authority(
                    self._source(source_video_id),
                    manifest_for_authority,
                )
        # A retry after DB persistence interruption must not repeat audio
        # staging or Phase-4 preflight when the exact hash-bound final already
        # passed Output QA. Validate the durable artifact first; fall through
        # to preparation only when any authority has changed.
        try:
            reusable_root = self.active_root(source_video_id)
        except QualityLocalizationError:
            reusable_root = None
        if reusable_root is not None and self._final_output_is_reusable(
            reusable_root, source_video_id
        ):
            if on_progress is not None:
                on_progress("adaptive_final_reused", 90)
            source = self._source(source_video_id)
            self._set_active_root(source, reusable_root, stage="FINAL_READY")
            self.db.commit()
            if on_progress is not None:
                on_progress("completed", 100)
            return reusable_root / "phase4_adaptive_final.mp4"

        root = self.prepare_final_audio(source_video_id, operator_id=operator_id)
        if self._final_output_is_reusable(root, source_video_id):
            if on_progress is not None:
                on_progress("adaptive_final_reused", 90)
            source = self._source(source_video_id)
            self._set_active_root(source, root, stage="FINAL_READY")
            self.db.commit()
            if on_progress is not None:
                on_progress("completed", 100)
            return root / "phase4_adaptive_final.mp4"
        if on_progress is not None:
            on_progress("adaptive_final_render", 20)
        if run_phase4_adaptive.run(
            root,
            visual_preview=False,
            on_progress=on_progress,
        ) != 0:
            raise QualityLocalizationError("Adaptive final render failed Output QA")
        final_path = root / "phase4_adaptive_final.mp4"
        if not final_path.is_file():
            raise QualityLocalizationError("Adaptive final video is missing")
        source = self._source(source_video_id)
        self._set_active_root(source, root, stage="FINAL_READY")
        self.db.commit()
        if on_progress is not None:
            on_progress("completed", 100)
        return final_path

    def _assert_tts_manifest_authority(
        self,
        source: SourceVideo,
        manifest: dict[str, Any],
    ) -> None:
        from src.tts_pipeline.errors import TtsPipelineError
        from src.tts_pipeline.services.profile_authority import (
            assert_manifest_tts_authority_active,
        )

        try:
            assert_manifest_tts_authority_active(
                self.db,
                source.workspace_id,
                manifest,
            )
        except TtsPipelineError as exc:
            raise QualityLocalizationError(exc.message) from exc

    def _final_output_is_reusable(self, root: Path, source_video_id: UUID) -> bool:
        """Reuse a hash-bound final PASS after DB persistence interruption."""
        meta = _read_object(root / "phase4_adaptive_render_meta.json", required=False)
        if (
            str(meta.get("status") or "") != "FINAL_RENDERED"
            or str(meta.get("output_qa_status") or "") != "PASS"
            or not bool(dict(meta.get("audio_mix") or {}).get("narration_complete"))
        ):
            return False
        output = (root / "phase4_adaptive_final.mp4").resolve()
        if (
            not output.is_relative_to(root)
            or not output.is_file()
            or _sha256_file(output) != str(meta.get("output_video_sha256") or "")
        ):
            return False
        input_path = root / "phase4_render_input.json"
        if _sha256_file(input_path) != str(meta.get("phase4_input_sha256") or ""):
            return False
        source_path = self._source_video_path(source_video_id)
        if _sha256_file(source_path) != str(meta.get("source_video_sha256") or ""):
            return False
        qa_path = root / "qa" / "phase4_adaptive_final_output_qa.json"
        qa = _read_object(qa_path, required=False)
        return (
            str(qa.get("status") or "") == "PASS"
            and not list(qa.get("failed_checks") or [])
        )

    def summary(self, source_video_id: UUID) -> dict[str, Any]:
        source = self._source(source_video_id)
        quality_state = dict(
            dict(source.metadata_json or {}).get(QUALITY_METADATA_KEY) or {}
        )
        analyze_recipe_ref = dict(
            quality_state.get("analyze_ocr_recipe_lock") or {}
        )
        from src.services.analyze_ocr_recipe import ANALYZE_OCR_RELEASE_LABEL

        try:
            root = self.active_root(source.id)
        except QualityLocalizationError:
            return {
                "workflow_version": QUALITY_WORKFLOW_VERSION,
                "workflow_stage": "NOT_STARTED",
                "artifact_run_id": None,
                "phase2_content_object_count": 0,
                "phase2_handoff_status": "NOT_STAGED",
                "phase2_blocked_reasons": [],
                "dialogue_translation_blocked_count": 0,
                "requires_dialogue_translation_approval": False,
                "review_objects": [],
                "translation_objects": [],
                "review_required": 0,
                "translation_review_required": 0,
                "visual_preview_asset_id": None,
                "can_render_final": False,
                "audio_review_status": "NOT_STAGED",
                "audio_mix_review_status": "NOT_STAGED",
                "audio_mix_preview_path": None,
                "audio_warnings": [],
                "timing_fit_summary": {},
                "residual_review_objects": [],
                "residual_proposal_objects": [],
                "residual_proposal_sha256": None,
                "residual_authority_sha256": None,
                "residual_translation_status": "NOT_REQUIRED",
                "residual_translation_input_sha256": None,
                "residual_translation_suggestion_count": 0,
                "provenance_counts": {},
                "protected_source_tracks": 0,
                "provenance_artifact_path": None,
                "analysis_engine": QUALITY_ANALYSIS_ENGINE,
                "analysis_recipe_release": ANALYZE_OCR_RELEASE_LABEL,
                "analysis_recipe_sha256": None,
                "pipeline_recipe_release": None,
                "pipeline_recipe_sha256": None,
                "analysis_metrics": {},
                "analysis_mode": None,
                "audio_window_count": 0,
                "visual_trigger_count": 0,
                "all_frame_proxy_size": None,
                "candidate_window_count": 0,
                "detector_frame_count": 0,
                "analysis_elapsed_s": None,
                "analysis_fallback_used": False,
            }
        phase1_meta = _read_object(root / "phase1_meta.json", required=False)
        event_metrics = _read_object(root / "phase1_event_metrics.json", required=False)
        phase2_meta = _read_object(root / "phase2_meta.json", required=False)
        phase2_handoff_preview = _read_object(
            root / "phase2_handoff_preview.json", required=False
        )
        phase2_handoff_status = str(
            phase2_meta.get("handoff_status")
            or phase2_handoff_preview.get("status")
            or "NOT_STAGED"
        )
        phase2_blocked_reasons = [
            str(value)
            for value in list(phase2_handoff_preview.get("blocked_reasons") or [])
            if str(value).strip()
        ]
        dialogue_translation_blocked_count = sum(
            reason.startswith("semantic_dialogue_translation_unapproved:")
            for reason in phase2_blocked_reasons
        )
        phase2_queue = _read_object(root / "phase2_review_queue.json", required=False)
        phase3_queue = _read_object(root / "phase3_review_queue.json", required=False)
        phase3_timeline = _read_object(
            root / "phase3_translation_timeline.json", required=False
        )
        review_objects = [
            self._phase2_review_row(row)
            for row in list(phase2_queue.get("content_objects") or [])
            if isinstance(row, Mapping)
        ]
        translation_rows = list(phase3_queue.get("content_objects") or [])
        # A closed Phase 3 run intentionally fossilizes the approved rows in
        # phase3_translation_timeline.json and leaves the review queue empty.
        # Keep those rows available so a failed/cancelled preview can be
        # retried from the frontend without rerunning OCR or translation.
        if not translation_rows:
            translation_rows = list(phase3_timeline.get("content_objects") or [])
        translation_objects = [
            self._phase3_review_row(row)
            for row in translation_rows
            if isinstance(row, Mapping)
        ]
        preview_asset = self.db.scalar(
            select(MediaAsset)
            .where(
                MediaAsset.source_video_id == source.id,
                MediaAsset.asset_type == MediaAssetType.CLEANED_VIDEO,
                MediaAsset.status == MediaAssetStatus.AVAILABLE,
                MediaAsset.is_current.is_(True),
            )
            .order_by(MediaAsset.version.desc())
            .limit(1)
        )
        active_artifact_root = root.relative_to(self.storage.root).as_posix()
        preview_output_qa = _read_object(
            root / "qa" / "phase4_adaptive_visual_preview_output_qa.json",
            required=False,
        )
        preview_qa_passed = str(preview_output_qa.get("status") or "") == "PASS"
        # Encoded Output QA is a separate authority from Phase 4 preflight.  A
        # preview may pass preflight and still expose a one-frame CJK residual
        # after encode (codec/scaler/font effects).  Surface that evidence to
        # the orchestrator so full-auto can remediate instead of parking at a
        # misleading "waiting visual review" stage.
        render_meta = _read_object(
            root / "phase4_adaptive_render_meta.json", required=False
        )
        encoded_residual = dict(preview_output_qa.get("residual_cjk") or {})
        rendered_video_name = str(
            dict(render_meta.get("artifacts") or {}).get("video") or ""
        )
        rendered_video = (root / rendered_video_name).resolve()
        render_input = root / "phase4_render_input.json"
        encoded_artifacts_current = bool(
            rendered_video_name
            and rendered_video.is_relative_to(root)
            and rendered_video.is_file()
            and render_input.is_file()
            and str(render_meta.get("phase4_input_sha256") or "")
            == _sha256_file(render_input)
            and str(render_meta.get("output_video_sha256") or "")
            == _sha256_file(rendered_video)
        )
        encoded_residual_current = (
            str(render_meta.get("status") or "") == "VISUAL_PREVIEW_QA_FAILED"
            and str(render_meta.get("output_qa_status") or "") == "FAIL"
            and "residual_cjk" in list(render_meta.get("output_qa_failed_checks") or [])
            and str(preview_output_qa.get("status") or "") == "FAIL"
            and "residual_cjk" in list(preview_output_qa.get("failed_checks") or [])
            and bool(encoded_residual.get("complete"))
            and encoded_artifacts_current
        )
        render_prep = _read_object(root / "render_prep_manifest.json", required=False)
        audio_review = dict(render_prep.get("audio_review") or {})
        mix_review = _read_object(
            root / "phase4_background_mix_review.json", required=False
        )
        mix_approval = _read_object(
            root / "phase4_background_mix_approval.json", required=False
        )
        audio_approval = _read_object(
            root / "phase4_audio_approval.json", required=False
        )
        no_dialogue_review = _read_object(
            root / "phase4_no_dialogue_audio_review.json", required=False
        )
        remediation_pointer = _read_object(
            root / "phase4_visual_remediation_active.json", required=False
        )
        active_remediation_sha256 = str(
            dict(remediation_pointer.get("active_ref") or {}).get("sha256") or ""
        )
        preflight_meta = _read_object(
            root / "phase4_preflight_meta.json", required=False
        )
        residual = (
            encoded_residual
            if encoded_residual_current
            else dict(preflight_meta.get("residual_cjk") or {})
        )
        residual_frames = list(residual.get("source_confirmation_frames") or [])
        phase4_input_path = (
            root / "phase4_render_input.json"
            if (root / "phase4_render_input.json").is_file()
            else root / "phase4_render_input_preview.json"
        )
        phase4_input = _read_object(phase4_input_path, required=False)
        video_meta = dict(phase4_input.get("video") or {})
        phase2_timeline = _read_object(
            root / "phase2_ocr_timeline.json", required=False
        )
        residual_review_objects, residual_normalization = (
            normalize_residual_detections(
                [
                    dict(raw)
                    for raw in list(residual.get("detections") or [])
                    if isinstance(raw, Mapping)
                ],
                protected_tracks=[
                    dict(raw)
                    for raw in list(phase2_timeline.get("protected_source_tracks") or [])
                    if isinstance(raw, Mapping)
                ],
                frame_width=int(video_meta.get("frame_width") or 0),
                frame_height=int(video_meta.get("frame_height") or 0),
                image_paths=[str(value) for value in residual_frames if str(value)],
            )
        )
        residual_authority_sha256 = (
            _sha256_file(root / "qa" / "phase4_adaptive_visual_preview_output_qa.json")
            if encoded_residual_current
            else _sha256_file(root / "phase4_preflight_meta.json")
            if residual_review_objects
            and (root / "phase4_preflight_meta.json").is_file()
            else None
        )
        residual_translation_input_sha256 = (
            _residual_translation_input_sha256(
                residual_review_objects,
                authority_sha256=residual_authority_sha256,
            )
            if residual_review_objects and residual_authority_sha256
            else None
        )
        residual_translation = _read_object(
            root / "phase2_residual_translation_suggestions.json",
            required=False,
        )
        residual_translation_status = (
            "NOT_REQUIRED" if not residual_review_objects else "NOT_STARTED"
        )
        residual_translation_suggestion_count = 0
        if residual_review_objects and residual_translation:
            if (
                str(residual_translation.get("status") or "")
                == "SUGGESTION_ONLY"
                and not bool(residual_translation.get("operator_approval_written"))
                and str(
                    residual_translation.get("residual_authority_sha256") or ""
                )
                == str(residual_authority_sha256 or "")
                and str(residual_translation.get("input_sha256") or "")
                == str(residual_translation_input_sha256 or "")
            ):
                suggestion_rows = [
                    dict(row)
                    for row in list(residual_translation.get("suggestions") or [])
                    if isinstance(row, Mapping)
                ]
                suggestion_by_content_id = {
                    str(row.get("content_id") or "").strip(): row
                    for row in suggestion_rows
                    if str(row.get("content_id") or "").strip()
                }
                suggestion_by_text = {
                    str(row.get("ocr_text") or "").strip(): row
                    for row in suggestion_rows
                    if str(row.get("ocr_text") or "").strip()
                }
                for row in residual_review_objects:
                    suggested = suggestion_by_content_id.get(
                        str(row.get("content_id") or "")
                    ) or suggestion_by_text.get(str(row.get("text") or "").strip())
                    if not suggested:
                        continue
                    corrected = str(
                        suggested.get("ocr_text_corrected") or ""
                    ).strip()
                    vi_text = str(suggested.get("vi_text_suggested") or "").strip()
                    if corrected:
                        row["ocr_text_corrected_suggested"] = corrected
                    if vi_text:
                        row["vi_text_suggested"] = vi_text
                    if corrected and vi_text:
                        residual_translation_suggestion_count += 1
                residual_translation_status = (
                    "READY"
                    if residual_translation_suggestion_count
                    == len(residual_review_objects)
                    else "PARTIAL"
                )
            else:
                residual_translation_status = "STALE"
        residual_proposal = _read_object(
            root / "phase2_residual_remediation_proposal_frontend.json",
            required=False,
        )
        residual_proposal_objects = [
            dict(row)
            for row in list(residual_proposal.get("proposals") or [])
            if isinstance(row, Mapping)
        ]
        active_phase2_remediation = _matching_active_residual_remediation(
            root,
            proposal_sha256=str(residual_proposal.get("proposal_sha256") or ""),
        )
        if active_phase2_remediation is not None:
            # The immutable proposal remains on disk for audit, but its
            # checkpoint is closed once the exact SHA is materialized.
            residual_proposal_objects = []
        if preview_asset is not None:
            asset_metadata = dict(getattr(preview_asset, "metadata_json", None) or {})
            # A failed preview does not register a new asset, so the database
            # may still point at a successful preview from the previous run.
            # Never let that stale asset unlock Approve for the active run.
            if (
                str(asset_metadata.get("artifact_root") or "")
                != active_artifact_root
                or not preview_qa_passed
                or str(asset_metadata.get("visual_remediation_sha256") or "")
                != active_remediation_sha256
            ):
                preview_asset = None
        if (root / "phase4_adaptive_final.mp4").is_file():
            stage = "FINAL_READY"
        elif residual_proposal_objects:
            # A validated proposal is the next explicit operator checkpoint.
            # The encoded residual QA intentionally remains current until that
            # proposal is approved/materialized, so it must not force the UI
            # back to triage and hide the newly built review artifact.
            stage = "WAITING_RESIDUAL_REVIEW"
        elif encoded_residual_current:
            # Must precede the generic preview stage: the encoded preview is
            # diagnostic evidence for remediation, not an operator review gate.
            stage = "WAITING_RESIDUAL_TRIAGE"
        elif (
            str(mix_approval.get("status") or "") == "AUDIO_MIX_APPROVED"
            or str(audio_approval.get("status") or "") == "AUDIO_APPROVED"
        ):
            stage = "AUDIO_APPROVED"
        elif (
            str(mix_review.get("status") or "") == "PENDING_AUDIO_MIX_REVIEW"
            or str(no_dialogue_review.get("status") or "") == "PENDING_AUDIO_REVIEW"
        ):
            stage = "WAITING_AUDIO_REVIEW"
        elif (root / "phase4_visual_approval.json").is_file():
            stage = "VISUAL_APPROVED"
        elif (
            str(preflight_meta.get("status") or "") == "PHASE4_PREFLIGHT_BLOCKED"
            and str(preflight_meta.get("final_render_gate") or "")
            == "BLOCKED_VISUAL_RESIDUAL_CJK"
        ):
            stage = "WAITING_RESIDUAL_TRIAGE"
        elif (root / "phase4_adaptive_visual_preview.mp4").is_file():
            stage = "WAITING_VISUAL_REVIEW"
        elif (root / "phase3_closeout.json").is_file():
            stage = "READY_FOR_VISUAL_PREVIEW"
        elif translation_objects:
            stage = "WAITING_TRANSLATION_REVIEW"
        elif bool(phase2_meta.get("ready_for_phase3")):
            stage = "PHASE3_PREPARING"
        elif review_objects:
            stage = "WAITING_OCR_REVIEW"
        elif dialogue_translation_blocked_count:
            # OCR geometry is complete, but dialogue hard-sub replacement is
            # intentionally fail-closed until the operator-approved Vietnamese
            # transcript authority exists.  This is an input checkpoint, not a
            # reason to run expensive Phase 1 again.
            stage = "WAITING_DIALOGUE_TRANSLATION_APPROVAL"
        elif phase2_handoff_status == "HANDOFF_BLOCKED":
            stage = "PHASE2_BLOCKED"
        else:
            stage = "PHASE2_READY"
        visual_approved = stage in {"VISUAL_APPROVED", "FINAL_READY"}
        visual_approved = visual_approved or (root / "phase4_visual_approval.json").is_file()
        audio_approved = (
            str(mix_approval.get("status") or "") == "AUDIO_MIX_APPROVED"
            or str(audio_approval.get("status") or "") == "AUDIO_APPROVED"
        )
        analysis_metrics = dict(
            phase1_meta.get("analysis_metrics") or event_metrics or {}
        )
        return {
            "workflow_version": QUALITY_WORKFLOW_VERSION,
            "workflow_stage": stage,
            "artifact_run_id": root.name,
            "artifact_root": active_artifact_root,
            "phase1_tracks": int(phase2_meta.get("tracks") or 0),
            "phase2_model_version": phase2_meta.get("model_version"),
            "phase2_content_object_count": int(
                phase2_meta.get("content_objects") or 0
            ),
            "phase2_handoff_status": phase2_handoff_status,
            "phase2_blocked_reasons": phase2_blocked_reasons,
            "dialogue_translation_blocked_count": (
                dialogue_translation_blocked_count
            ),
            "requires_dialogue_translation_approval": bool(
                dialogue_translation_blocked_count
            ),
            "local_recovery_summary": dict(
                phase2_meta.get("local_recovery_summary") or {}
            ),
            "provenance_counts": dict(phase2_meta.get("provenance_counts") or {}),
            "protected_source_tracks": int(
                phase2_meta.get("protected_source_tracks") or 0
            ),
            "provenance_artifact_path": phase2_meta.get("provenance_artifact"),
            "analysis_engine": str(
                phase1_meta.get("analysis_engine")
                or event_metrics.get("analysis_engine")
                or QUALITY_ANALYSIS_ENGINE
            ),
            "analysis_recipe_release": str(
                analyze_recipe_ref.get("release_label")
                or ANALYZE_OCR_RELEASE_LABEL
            ),
            "analysis_recipe_sha256": str(
                analyze_recipe_ref.get("recipe_sha256") or ""
            ) or None,
            "pipeline_recipe_release": str(
                dict(quality_state.get("pipeline_recipe_lock") or {}).get(
                    "release_label"
                )
                or ""
            ) or None,
            "pipeline_recipe_sha256": str(
                dict(quality_state.get("pipeline_recipe_lock") or {}).get(
                    "recipe_sha256"
                )
                or ""
            ) or None,
            "analysis_metrics": analysis_metrics,
            "analysis_mode": str(
                analysis_metrics.get("candidate_seed_mode") or "VISUAL_ONLY"
            ),
            "audio_window_count": int(
                analysis_metrics.get("audio_window_count") or 0
            ),
            "visual_trigger_count": int(
                analysis_metrics.get("visual_trigger_count") or 0
            ),
            "all_frame_proxy_size": (
                [int(value) for value in analysis_metrics.get("all_frame_proxy_size")]
                if isinstance(analysis_metrics.get("all_frame_proxy_size"), list)
                and len(analysis_metrics["all_frame_proxy_size"]) == 2
                else None
            ),
            "candidate_window_count": int(
                analysis_metrics.get("candidate_window_count")
                or 0
            ),
            "detector_frame_count": int(
                analysis_metrics.get("detector_frames")
                or 0
            ),
            "analysis_elapsed_s": (
                float(phase1_meta.get("elapsed_s"))
                if phase1_meta.get("elapsed_s") is not None
                else None
            ),
            "analysis_fallback_used": bool(
                analysis_metrics.get("fallback_used")
            ),
            "review_objects": review_objects,
            "translation_objects": translation_objects,
            "review_required": len(review_objects),
            "translation_review_required": len(translation_objects),
            "visual_preview_asset_id": str(preview_asset.id) if preview_asset else None,
            # The public OCR summary historically exposes the player source as
            # cleaned_video_asset_id.  Override the legacy OCR asset with the
            # QA-bound quality preview (or null after a failed active run).
            "cleaned_video_asset_id": str(preview_asset.id) if preview_asset else None,
            "visual_approved": visual_approved,
            "can_render_final": visual_approved and audio_approved,
            "audio_review_status": str(audio_review.get("status") or "NOT_STAGED"),
            "audio_mix_review_status": str(
                mix_approval.get("status")
                or audio_approval.get("status")
                or mix_review.get("status")
                or no_dialogue_review.get("status")
                or "NOT_STAGED"
            ),
            "audio_mix_preview_path": (
                "phase4_audio_mix_preview.wav"
                if (root / "phase4_audio_mix_preview.wav").is_file()
                else (
                    "phase4_no_dialogue_source_audio.wav"
                    if (root / "phase4_no_dialogue_source_audio.wav").is_file()
                    else None
                )
            ),
            "audio_warnings": list(render_prep.get("warnings") or []),
            "timing_fit_summary": dict(render_prep.get("timing_fit_summary") or {}),
            "residual_review_objects": residual_review_objects,
            "residual_normalization": residual_normalization,
            "residual_proposal_objects": residual_proposal_objects,
            "residual_proposal_sha256": (
                residual_proposal.get("proposal_sha256")
                if residual_proposal_objects
                else None
            ),
            "residual_translation_status": residual_translation_status,
            "residual_translation_input_sha256": (
                residual_translation_input_sha256
            ),
            "residual_translation_suggestion_count": (
                residual_translation_suggestion_count
            ),
            "residual_authority_source": (
                "encoded_visual_preview_output_qa"
                if encoded_residual_current
                else "phase4_preflight"
                if residual_review_objects
                else None
            ),
            "encoded_output_qa_current": encoded_residual_current,
            "residual_authority_sha256": residual_authority_sha256,
        }

    def artifact_path(self, source_video_id: UUID, relative_path: str) -> Path:
        root = self.active_root(source_video_id)
        candidate = (root / str(relative_path or "")).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise QualityLocalizationError("Localization artifact was not found")
        return candidate

    def _write_phase2_decisions(
        self,
        root: Path,
        *,
        decisions: list[Mapping[str, Any]],
        operator_id: str,
    ) -> None:
        queue_path = root / "phase2_review_queue.json"
        queue = _read_object(queue_path)
        queue_rows = [
            dict(row)
            for row in list(queue.get("content_objects") or [])
            if isinstance(row, Mapping)
        ]
        expected_ids = {str(row.get("content_id") or "") for row in queue_rows}
        supplied = {
            str(row.get("content_id") or ""): dict(row)
            for row in decisions
            if isinstance(row, Mapping)
        }
        if not expected_ids or set(supplied) != expected_ids:
            raise QualityLocalizationError(
                "OCR decisions must cover every current review object"
            )
        payload: dict[str, Any] = {
            "schema_version": "phase2_frontend_decisions_v1",
            "review_queue_sha256": _sha256_file(queue_path),
            "reviewer": str(operator_id or "frontend_operator"),
            "reviewed_at": _now(),
            "decisions": [],
        }
        for content_id, row in supplied.items():
            decision = str(row.get("decision") or "APPROVE").strip().upper()
            approved_text = str(
                row.get("ocr_text_approved")
                or next(
                    (
                        item.get("ocr_text_candidate")
                        for item in queue_rows
                        if str(item.get("content_id") or "") == content_id
                    ),
                    "",
                )
                or ""
            ).strip()
            if decision in {"APPROVE", "EDIT"} and not approved_text:
                raise QualityLocalizationError(
                    f"OCR decision {decision} for {content_id} requires non-empty approved text; "
                    "use EDIT with corrected text, PRESERVE_SOURCE, or REJECT_UI"
                )
            payload["decisions"].append(
                {
                    "content_id": content_id,
                    "decision": decision,
                    "ocr_text_approved": approved_text,
                    "vi_text_approved": row.get("vi_text_approved"),
                }
            )
        payload["decisions_sha256"] = _sha256_json(payload)
        path = root / "phase2_frontend_decisions.json"
        _write_json_atomic(path, payload)
        apply_phase2_operator_review(root_dir=root, decisions_path=path)

    def _phase1_is_reusable(
        self,
        root: Path,
        video_path: Path,
        *,
        analysis_engine: str = QUALITY_ANALYSIS_ENGINE,
        candidate_seed_sha256: str = "",
    ) -> bool:
        authority = _read_object(root / "quality_phase1_authority.json", required=False)
        timeline = root / "master_timeline.json"
        meta = root / "phase1_meta.json"
        provenance = root / "visual_text_provenance_v2.json"
        candidate_windows = root / "phase1_candidate_windows_v1.json"
        event_metrics = root / "phase1_event_metrics.json"
        track_coverage = root / "phase1_track_coverage_v2.json"
        if (
            not authority
            or not timeline.is_file()
            or not meta.is_file()
            or not provenance.is_file()
            or not candidate_windows.is_file()
            or not event_metrics.is_file()
            or not track_coverage.is_file()
        ):
            return False
        try:
            claimed_authority_hash = str(authority.get("authority_sha256") or "")
            unsigned_authority = dict(authority)
            unsigned_authority.pop("authority_sha256", None)
            return (
                len(claimed_authority_hash) == 64
                and claimed_authority_hash == _sha256_json(unsigned_authority)
                and str(authority.get("workflow_version") or "") == QUALITY_WORKFLOW_VERSION
                and str(authority.get("analysis_engine") or "")
                == str(analysis_engine)
                and str(authority.get("candidate_seed_sha256") or "")
                == str(candidate_seed_sha256)
                and int(authority.get("step") or 0) == 1
                and int(authority.get("pad") or 0) == 1
                and str(authority.get("source_sha256") or "") == _sha256_file(video_path)
                and str(authority.get("timeline_sha256") or "") == _sha256_file(timeline)
                and str(authority.get("phase1_meta_sha256") or "") == _sha256_file(meta)
                and str(authority.get("provenance_sha256") or "")
                == _sha256_file(provenance)
                and str(authority.get("temporal_scan_policy") or "")
                == QUALITY_ANALYSIS_POLICY
                and str(authority.get("candidate_windows_sha256") or "")
                == _sha256_file(candidate_windows)
                and str(authority.get("event_metrics_sha256") or "")
                == _sha256_file(event_metrics)
                and str(authority.get("track_coverage_sha256") or "")
                == _sha256_file(track_coverage)
            )
        except OSError:
            return False

    def _record_phase1_authority(
        self,
        root: Path,
        video_path: Path,
        *,
        analysis_engine: str,
        candidate_seed_sha256: str,
    ) -> None:
        timeline = root / "master_timeline.json"
        meta = root / "phase1_meta.json"
        provenance = root / "visual_text_provenance_v2.json"
        candidate_windows = root / "phase1_candidate_windows_v1.json"
        event_metrics = root / "phase1_event_metrics.json"
        track_coverage = root / "phase1_track_coverage_v2.json"
        if (
            not timeline.is_file()
            or not meta.is_file()
            or not provenance.is_file()
            or not candidate_windows.is_file()
            or not event_metrics.is_file()
            or not track_coverage.is_file()
        ):
            raise QualityLocalizationError("Phase 1 authority artifacts are incomplete")
        payload = {
            "schema_version": "quality_phase1_runtime_authority_v2",
            "workflow_version": QUALITY_WORKFLOW_VERSION,
            "analysis_engine": str(analysis_engine),
            "candidate_seed_sha256": str(candidate_seed_sha256),
            "source_sha256": _sha256_file(video_path),
            "timeline_sha256": _sha256_file(timeline),
            "phase1_meta_sha256": _sha256_file(meta),
            "provenance_sha256": _sha256_file(provenance),
            "step": 1,
            "pad": 1,
            "temporal_scan_policy": QUALITY_ANALYSIS_POLICY,
            "candidate_windows_sha256": _sha256_file(candidate_windows),
            "event_metrics_sha256": _sha256_file(event_metrics),
            "track_coverage_sha256": _sha256_file(track_coverage),
            "authority_v3_6_full_duration": False,
            "recorded_at": _now(),
        }
        payload["authority_sha256"] = _sha256_json(payload)
        _write_json_atomic(root / "quality_phase1_authority.json", payload)

    def _run_phase2_with_semantic_authority(
        self,
        *,
        source: SourceVideo,
        root: Path,
        video_path: Path,
    ) -> int:
        """Run Phase 2 against a fresh, DB-backed dialogue authority.

        Phase 2 owns visual geometry. Current transcript/token timing and an
        operator-approved Vietnamese translation own dialogue meaning. Writing
        the bridge immediately before every Phase-2 invocation prevents a
        retry, OCR approval rerun, or residual-remediation resume from silently
        falling back to fragmented OCR strings.
        """

        self._write_semantic_dialogue_authority(source, root)
        try:
            return run_phase2_only.main(
                ["--provider", "local", str(root), str(video_path)]
            )
        except RuntimeError as exc:
            raise QualityLocalizationError(
                f"Phase 2 OCR delta failed: {exc}"
            ) from exc

    def _write_semantic_dialogue_authority(
        self,
        source: SourceVideo,
        root: Path,
    ) -> Path:
        phase1_path = root / "master_timeline.json"
        if not phase1_path.is_file():
            raise QualityLocalizationError(
                "Cannot build semantic dialogue authority before Phase 1"
            )

        transcript_rows = list(
            self.db.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.source_video_id == source.id,
                    TranscriptSegment.is_current.is_(True),
                )
                .order_by(
                    TranscriptSegment.segment_index.asc(),
                    TranscriptSegment.version.desc(),
                )
            ).all()
        )
        translation_rows = list(
            self.db.scalars(
                select(TranslationSegment)
                .where(
                    TranslationSegment.source_video_id == source.id,
                    TranslationSegment.language_code == "vi",
                    TranslationSegment.is_current.is_(True),
                )
                .order_by(
                    TranslationSegment.segment_index.asc(),
                    TranslationSegment.version.desc(),
                )
            ).all()
        )
        translation_by_transcript: dict[UUID, TranslationSegment] = {}
        for row in translation_rows:
            translation_by_transcript.setdefault(row.transcript_segment_id, row)

        segments: list[dict[str, Any]] = []
        seen_indices: set[int] = set()
        semantic_recipe_versions: set[str] = set()
        for row in transcript_rows:
            segment_index = int(row.segment_index)
            if segment_index in seen_indices:
                continue
            seen_indices.add(segment_index)
            metadata = dict(row.metadata_json or {})
            raw_payload = dict(metadata.get("raw_payload") or {})
            segmentation = dict(raw_payload.get("semantic_segmentation") or {})
            recipe_version = str(segmentation.get("recipe_version") or "").strip()
            if recipe_version:
                semantic_recipe_versions.add(recipe_version)
            translation = translation_by_transcript.get(row.id)
            translation_payload: dict[str, Any] | None = None
            if translation is not None:
                translation_status = getattr(
                    translation.status, "value", str(translation.status)
                )
                translation_payload = {
                    "translation_segment_id": str(translation.id),
                    "version": int(translation.version),
                    "text": str(translation.text or ""),
                    "status": str(translation_status),
                    "duration_budget_ms": translation.duration_budget_ms,
                }
            transcript_status = getattr(row.status, "value", str(row.status))
            segments.append(
                {
                    "transcript_segment_id": str(row.id),
                    "segment_index": segment_index,
                    "version": int(row.version),
                    "analysis_version": row.analysis_version,
                    "start_ms": int(row.start_ms),
                    "end_ms": int(row.end_ms),
                    "text": str(row.text or ""),
                    "status": str(transcript_status),
                    "speaker_label": row.speaker_label,
                    "raw_payload": raw_payload,
                    "translation": translation_payload,
                }
            )

        source_metadata = dict(source.metadata_json or {})
        has_speech = source_metadata.get("has_speech")
        dialogue_phase = str(source_metadata.get("dialogue_phase") or "")
        no_dialogue_confirmed = bool(
            has_speech is False or dialogue_phase == "no_dialogue"
        )
        if not segments and not no_dialogue_confirmed:
            raise QualityLocalizationError(
                "Semantic hard-sub requires current Analyze Audio transcript "
                "authority; re-run Analyze Audio before Analyze OCR"
            )
        if segments and not semantic_recipe_versions:
            raise QualityLocalizationError(
                "Semantic hard-sub requires word-timestamp authority from the "
                "current Analyze Audio recipe; re-run Analyze Audio"
            )

        segment_authority_sha256 = _sha256_json({"segments": segments})
        phase1_ref = {
            "path": phase1_path.name,
            "sha256": _sha256_file(phase1_path),
        }
        payload: dict[str, Any] = {
            "schema_version": "semantic_dialogue_authority_v1",
            "source_video_id": str(source.id),
            "phase1_ref": phase1_ref,
            "dialogue_state": {
                "has_speech": has_speech,
                "dialogue_phase": dialogue_phase or None,
                "no_dialogue_confirmed": no_dialogue_confirmed,
            },
            "authority_ref": {
                "phase1_sha256": phase1_ref["sha256"],
                "segment_authority_sha256": segment_authority_sha256,
                "semantic_dialogue_recipe_versions": sorted(
                    semantic_recipe_versions
                ),
            },
            "segments": segments,
        }
        payload["authority_sha256"] = _sha256_json(payload)
        path = root / "semantic_dialogue_authority.json"
        _write_json_atomic(path, payload)
        return path

    def _persist_phase2_db(
        self, source: SourceVideo, root: Path, *, job_id: UUID
    ) -> None:
        from src.ocr_pipeline.media_ocr_adapter import frame_results_from_ocr_payload
        from src.ocr_pipeline.services.ocr_service import OcrPipelineService

        payload = _read_object(root / "ocr_payload.json", required=False)
        if not payload:
            payload = _read_object(root / "phase2_ocr_payload_preview.json")
        phase2 = _read_object(root / "phase2_ocr_timeline.json")
        service = OcrPipelineService(self.db, storage=self.storage)
        service._clear_previous_ocr_rows(source.id)
        service._mark_previous_ocr_assets_non_current(source.id, include_cleaned=False)
        if list(phase2.get("content_objects") or []):
            text_object_count, frame_detection_count = service._persist_phase2_tracks(
                source,
                phase2_contract=phase2,
                payload=payload,
            )
        else:
            # Legacy quality artifacts predate the temporal content contract.
            # They remain readable, but are never preferred over Phase 2.
            frames = frame_results_from_ocr_payload(payload)
            frame_detection_count = service._persist_detections(
                source, frames, band_ratio=0.28
            )
            text_object_count = frame_detection_count
        context = service._storage_context(source)
        service._persist_json_asset(
            source,
            context,
            MediaAssetType.OCR_EVENTS,
            {
                "pipeline_version": QUALITY_WORKFLOW_VERSION,
                "provider": "local_phase2",
                "relational_projection": {
                    "authority": "phase2_content_object",
                    "text_object_count": text_object_count,
                    "frame_detection_count": frame_detection_count,
                    "empty_objects_persisted": 0,
                },
                "hardsub_events": [],
                "warnings": [],
                "clean_produced": False,
                "workflow": self.summary(source.id),
                "phase2": phase2,
            },
            filename=f"{QUALITY_WORKFLOW_VERSION}_phase2.json",
            manifest_group="quality_phase2",
            job_id=job_id,
        )
        self.db.flush()

    def _register_workspace_file(
        self,
        source: SourceVideo,
        path: Path,
        *,
        asset_type: MediaAssetType,
        manifest_group: str,
        job_id: UUID,
        metadata: Mapping[str, Any],
    ) -> MediaAsset:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.storage.root) or not resolved.is_file():
            raise QualityLocalizationError("Workspace output is outside local storage")
        storage_key = resolved.relative_to(self.storage.root).as_posix()
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source.id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.is_current.is_(True),
            )
            .values(is_current=False)
        )
        version = int(
            self.db.scalar(
                select(func.max(MediaAsset.version)).where(
                    MediaAsset.source_video_id == source.id,
                    MediaAsset.asset_type == asset_type,
                )
            )
            or 0
        ) + 1
        # A retry of the same durable run writes the same artifact path.  The
        # workspace storage-key unique constraint makes inserting another row
        # unsafe; rebind the existing row instead.  This is also what makes a
        # worker crash after render/QA resume idempotently from the persisted
        # video rather than getting converted into WORKER_ORPHANED.
        existing = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.workspace_id == source.workspace_id,
                MediaAsset.storage_key == storage_key,
            )
        )
        if existing is not None:
            existing.source_video_id = source.id
            existing.asset_type = asset_type
            existing.status = MediaAssetStatus.AVAILABLE
            existing.is_current = True
            existing.manifest_group = manifest_group
            existing.created_by_job_id = job_id
            existing.mime_type = "video/mp4"
            existing.size_bytes = resolved.stat().st_size
            existing.checksum_sha256 = _sha256_file(resolved)
            existing.metadata_json = dict(metadata)
            existing.error_message = None
            self.db.flush()
            return existing
        asset = MediaAsset(
            workspace_id=source.workspace_id,
            source_video_id=source.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=version,
            storage_provider=self.storage.provider_name,
            storage_key=storage_key,
            relative_path=storage_key,
            manifest_group=manifest_group,
            is_current=True,
            created_by_job_id=job_id,
            mime_type="video/mp4",
            size_bytes=resolved.stat().st_size,
            checksum_sha256=_sha256_file(resolved),
            metadata_json=dict(metadata),
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _phase2_review_row(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(raw)
        assets = [dict(value) for value in list(row.get("review_assets") or [])]
        first = assets[0] if assets else {}
        return {
            "content_id": row.get("content_id"),
            "ocr_text_candidate": row.get("ocr_text_candidate"),
            "roles": list(row.get("roles") or []),
            "review_input_sha256": row.get("review_input_sha256"),
            "start_frame": first.get("start_frame"),
            "end_frame": first.get("end_frame"),
            "image_path": first.get("overlay_path") or first.get("best_keyframe_path"),
            "provenance_classifications": list(
                row.get("provenance_classifications") or []
            ),
            "visual_provenance": dict(first.get("visual_provenance") or {}),
        }

    def _phase3_review_row(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(raw)
        return {
            "content_id": row.get("content_id"),
            "zh_approved": row.get("zh_approved"),
            # Closed Phase 3 fossils carry both the original candidate and the
            # operator-approved wording. Preview retry must preserve the
            # approved wording instead of silently reverting translations.
            "vi_text_candidate": row.get("vi_text_approved")
            or row.get("vi_text_candidate"),
            "roles": list(row.get("roles") or []),
            "quality_flags": list(row.get("quality_flags") or []),
            "review_input_sha256": row.get("review_input_sha256"),
        }

    def _set_active_root(
        self,
        source: SourceVideo,
        root: Path,
        *,
        stage: str,
        recipe_reference: Mapping[str, Any] | None = None,
        analyze_recipe_reference: Mapping[str, Any] | None = None,
    ) -> None:
        meta = dict(source.metadata_json or {})
        state = dict(meta.get(QUALITY_METADATA_KEY) or {})
        state.update({
            "workflow_version": QUALITY_WORKFLOW_VERSION,
            "active_root": root.relative_to(self.storage.root).as_posix(),
            "stage": stage,
            "updated_at": _now(),
        })
        if recipe_reference:
            state["pipeline_recipe_lock"] = dict(recipe_reference)
        if analyze_recipe_reference:
            state["analyze_ocr_recipe_lock"] = dict(
                analyze_recipe_reference
            )
        meta[QUALITY_METADATA_KEY] = state
        source.metadata_json = meta
        self.db.flush()

    def _source(self, source_video_id: UUID) -> SourceVideo:
        source = self.db.get(SourceVideo, source_video_id)
        if source is None:
            raise QualityLocalizationError("Source video was not found")
        return source

    def _current_asset(
        self, source_video_id: UUID, asset_type: MediaAssetType
    ) -> MediaAsset | None:
        return self.db.scalar(
            select(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.status == MediaAssetStatus.AVAILABLE,
                MediaAsset.is_current.is_(True),
            )
            .order_by(MediaAsset.version.desc())
            .limit(1)
        )

    def _source_video_path(self, source_video_id: UUID) -> Path:
        asset = self._current_asset(source_video_id, MediaAssetType.SOURCE_VIDEO_RAW)
        if asset is None:
            raise QualityLocalizationError("Current source video asset is missing")
        path = self.storage.resolve(asset.storage_key).absolute_path
        if not path.is_file():
            raise QualityLocalizationError("Current source video file is missing")
        return path
