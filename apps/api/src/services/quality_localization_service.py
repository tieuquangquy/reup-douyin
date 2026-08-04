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
)
from scripts.rebind_phase3_approvals_after_residual_remediation import (
    Phase3ApprovalRebindError,
    rebind_approvals as rebind_phase3_approvals,
)
from src.core.settings import get_settings
from src.enums import JobType, MediaAssetStatus, MediaAssetType
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
from src.models.media import MediaAsset
from src.services.phase2_operator_review import apply_phase2_operator_review
from src.services.job_service import JobService
from src.storage.local import LocalStorageBackend


QUALITY_WORKFLOW_VERSION = "QUALITY_LOCALIZATION_V24_1"
QUALITY_TEMPORAL_SCAN_POLICY = "temporal_visual_localization_v2_4"
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
    ):
        from src.services.pipeline_recipe_runtime import bind_job_to_recipe_reference

        source = self._source(source_video_id)
        state = dict(dict(source.metadata_json or {}).get(QUALITY_METADATA_KEY) or {})
        recipe_reference = state.get("pipeline_recipe_lock")
        if not isinstance(recipe_reference, dict) or not recipe_reference:
            raise QualityLocalizationError("Quality workflow has no bound recipe")
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
            },
            idempotency_key=None,
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
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        from src.models.jobs import Job

        recipe_reference: dict[str, Any] | None = None
        owner_job = self.db.get(Job, job_id)
        if owner_job is not None:
            candidate = dict(owner_job.payload_json or {}).get("pipeline_recipe_lock")
            if isinstance(candidate, dict) and candidate:
                recipe_reference = dict(candidate)
        video_path = self._source_video_path(source.id)
        mode = str(action or "analyze")

        def progress(phase: str, percent: int) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        phase2_already_approved = False
        if mode == "analyze":
            root: Path | None = None
            if not force_refresh:
                try:
                    candidate = self.active_root(source.id)
                except QualityLocalizationError:
                    candidate = None
                if candidate is not None and self._phase1_is_reusable(candidate, video_path):
                    root = candidate
            if root is None:
                root = self.create_run_root(source.id, job_id)
            if self._phase1_is_reusable(root, video_path):
                progress("phase1_reused", 40)
            else:
                progress("phase1_v58", 3)

                def phase1_progress(phase: str, current: int, total: int) -> None:
                    ratio = max(0.0, min(1.0, float(current) / max(1.0, float(total))))
                    if phase in {"phase1_scan", "phase1_resume_decode"}:
                        percent = 3 + int(ratio * 32)
                    elif phase == "phase1_dense_rescan":
                        percent = 35 + int(ratio * 5)
                    else:
                        percent = 41
                    progress(f"{phase}|{current}|{total}", percent)

                if self._run_phase1_subprocess(
                    video_path=video_path,
                    root=root,
                    on_progress=phase1_progress,
                ) != 0:
                    raise QualityLocalizationError("Phase 1 v58 failed")
                self._record_phase1_authority(root, video_path)
            progress("phase1_complete", 45)
            self._set_active_root(
                source,
                root,
                stage="PHASE1_COMPLETE",
                recipe_reference=recipe_reference,
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
            if run_phase2_only.main(
                ["--provider", "local", str(root), str(video_path)]
            ) != 0:
                raise QualityLocalizationError("Phase 2 local OCR failed")
        progress("phase2_persist", 88)
        self._persist_phase2_db(source, root, job_id=job_id)
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

        progress("adaptive_preflight", 30)
        if run_phase4_preflight.main([str(root)]) != 0:
            preflight_meta = _read_object(root / "phase4_preflight_meta.json", required=False)
            gate = str(preflight_meta.get("final_render_gate") or "").strip()
            status = str(preflight_meta.get("status") or "").strip()
            if gate == "BLOCKED_VISUAL_RESIDUAL_CJK":
                self._set_active_root(source, root, stage="WAITING_RESIDUAL_TRIAGE")
                self.db.commit()
                progress("residual_review_required", 100)
                return self.summary(source.id)
            if status == "PHASE4_PREFLIGHT_BLOCKED" or gate.startswith("BLOCKED_"):
                raise QualityLocalizationError(
                    f"Adaptive Phase 4 preflight blocked: {gate or status or 'QUALITY_PREFLIGHT_BLOCKED'}"
                )
            raise QualityLocalizationError("Adaptive Phase 4 preflight failed")
        progress("adaptive_visual_preview", 45)
        if self._visual_preview_is_reusable(root):
            # A worker crash after encoded QA but before DB asset persistence
            # must resume at the durable artifact boundary, not render the same
            # 73-second video again.
            progress("adaptive_visual_preview_reused", 90)
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
        """Build or approve a residual-CJK delta, then resume from Phase 2 only."""

        source = self._source(source_video_id)
        root = self.active_root(source.id)

        def progress(phase: str, percent: int) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        mode = str(action or "")
        proposal_path = root / "phase2_residual_remediation_proposal_frontend.json"
        if mode == "build_residual_proposal":
            suggestion_payload = {
                "schema_version": "phase2_residual_translation_suggestions_v1",
                "status": "SUGGESTION_ONLY",
                "operator_approval_written": False,
                "created_at": _now(),
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
        if not proposal_path.is_file():
            raise QualityLocalizationError("Residual remediation proposal is missing")
        progress("residual_materialize", 10)
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
        progress("phase2_delta", 25)
        if run_phase2_only.main(["--provider", "local", str(root), str(self._source_video_path(source.id))]) != 0:
            raise QualityLocalizationError("Residual Phase 2 rerun failed")
        progress("phase3_rebind", 45)
        if run_phase3_only.main([str(root)]) != 0:
            raise QualityLocalizationError("Residual Phase 3 staging failed")
        try:
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

    def _run_phase1_subprocess(
        self,
        *,
        video_path: Path,
        root: Path,
        on_progress: Callable[[str, int, int], None],
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
        if run_phase4_adaptive.main([str(root), "--final"]) != 0:
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
        try:
            root = self.active_root(source.id)
        except QualityLocalizationError:
            return {
                "workflow_version": QUALITY_WORKFLOW_VERSION,
                "workflow_stage": "NOT_STARTED",
                "artifact_run_id": None,
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
                "provenance_counts": {},
                "protected_source_tracks": 0,
                "provenance_artifact_path": None,
            }
        phase2_meta = _read_object(root / "phase2_meta.json", required=False)
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
        residual = dict(preflight_meta.get("residual_cjk") or {})
        residual_frames = list(residual.get("source_confirmation_frames") or [])
        residual_review_objects = []
        for index, raw in enumerate(list(residual.get("detections") or [])):
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row["content_id"] = f"residual_{index + 1:03d}"
            row["image_path"] = (
                residual_frames[min(index, len(residual_frames) - 1)]
                if residual_frames
                else None
            )
            residual_review_objects.append(row)
        residual_proposal = _read_object(
            root / "phase2_residual_remediation_proposal_frontend.json",
            required=False,
        )
        residual_proposal_objects = [
            dict(row)
            for row in list(residual_proposal.get("proposals") or [])
            if isinstance(row, Mapping)
        ]
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
        elif (root / "phase4_adaptive_visual_preview.mp4").is_file():
            stage = "WAITING_VISUAL_REVIEW"
        elif residual_proposal_objects:
            stage = "WAITING_RESIDUAL_REVIEW"
        elif (
            str(preflight_meta.get("status") or "") == "PHASE4_PREFLIGHT_BLOCKED"
            and str(preflight_meta.get("final_render_gate") or "")
            == "BLOCKED_VISUAL_RESIDUAL_CJK"
        ):
            stage = "WAITING_RESIDUAL_TRIAGE"
        elif (root / "phase3_closeout.json").is_file():
            stage = "READY_FOR_VISUAL_PREVIEW"
        elif translation_objects:
            stage = "WAITING_TRANSLATION_REVIEW"
        elif bool(phase2_meta.get("ready_for_phase3")):
            stage = "PHASE3_PREPARING"
        elif review_objects:
            stage = "WAITING_OCR_REVIEW"
        else:
            stage = "PHASE2_READY"
        visual_approved = stage in {"VISUAL_APPROVED", "FINAL_READY"}
        visual_approved = visual_approved or (root / "phase4_visual_approval.json").is_file()
        audio_approved = (
            str(mix_approval.get("status") or "") == "AUDIO_MIX_APPROVED"
            or str(audio_approval.get("status") or "") == "AUDIO_APPROVED"
        )
        return {
            "workflow_version": QUALITY_WORKFLOW_VERSION,
            "workflow_stage": stage,
            "artifact_run_id": root.name,
            "artifact_root": active_artifact_root,
            "phase1_tracks": int(phase2_meta.get("tracks") or 0),
            "phase2_model_version": phase2_meta.get("model_version"),
            "provenance_counts": dict(phase2_meta.get("provenance_counts") or {}),
            "protected_source_tracks": int(
                phase2_meta.get("protected_source_tracks") or 0
            ),
            "provenance_artifact_path": phase2_meta.get("provenance_artifact"),
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
            "residual_proposal_objects": residual_proposal_objects,
            "residual_proposal_sha256": residual_proposal.get("proposal_sha256"),
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
            "decisions": [
                {
                    "content_id": content_id,
                    "decision": str(row.get("decision") or "APPROVE").upper(),
                    "ocr_text_approved": str(
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
                    ),
                    "vi_text_approved": row.get("vi_text_approved"),
                }
                for content_id, row in supplied.items()
            ],
        }
        payload["decisions_sha256"] = _sha256_json(payload)
        path = root / "phase2_frontend_decisions.json"
        _write_json_atomic(path, payload)
        apply_phase2_operator_review(root_dir=root, decisions_path=path)

    def _phase1_is_reusable(self, root: Path, video_path: Path) -> bool:
        authority = _read_object(root / "quality_phase1_authority.json", required=False)
        timeline = root / "master_timeline.json"
        meta = root / "phase1_meta.json"
        provenance = root / "visual_text_provenance_v2.json"
        if (
            not authority
            or not timeline.is_file()
            or not meta.is_file()
            or not provenance.is_file()
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
                and int(authority.get("step") or 0) == 1
                and int(authority.get("pad") or 0) == 1
                and str(authority.get("source_sha256") or "") == _sha256_file(video_path)
                and str(authority.get("timeline_sha256") or "") == _sha256_file(timeline)
                and str(authority.get("phase1_meta_sha256") or "") == _sha256_file(meta)
                and str(authority.get("provenance_sha256") or "")
                == _sha256_file(provenance)
                and str(authority.get("temporal_scan_policy") or "")
                == QUALITY_TEMPORAL_SCAN_POLICY
            )
        except OSError:
            return False

    def _record_phase1_authority(self, root: Path, video_path: Path) -> None:
        timeline = root / "master_timeline.json"
        meta = root / "phase1_meta.json"
        provenance = root / "visual_text_provenance_v2.json"
        if not timeline.is_file() or not meta.is_file() or not provenance.is_file():
            raise QualityLocalizationError("Phase 1 authority artifacts are incomplete")
        payload = {
            "schema_version": "quality_phase1_runtime_authority_v2",
            "workflow_version": QUALITY_WORKFLOW_VERSION,
            "source_sha256": _sha256_file(video_path),
            "timeline_sha256": _sha256_file(timeline),
            "phase1_meta_sha256": _sha256_file(meta),
            "provenance_sha256": _sha256_file(provenance),
            "step": 1,
            "pad": 1,
            "temporal_scan_policy": QUALITY_TEMPORAL_SCAN_POLICY,
            "authority_v3_6_full_duration": False,
            "recorded_at": _now(),
        }
        payload["authority_sha256"] = _sha256_json(payload)
        _write_json_atomic(root / "quality_phase1_authority.json", payload)

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
        frames = frame_results_from_ocr_payload(payload)
        service._persist_detections(source, frames, band_ratio=0.28)
        context = service._storage_context(source)
        service._persist_json_asset(
            source,
            context,
            MediaAssetType.OCR_EVENTS,
            {
                "pipeline_version": QUALITY_WORKFLOW_VERSION,
                "provider": "local_phase2",
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
