"""Advance Reup Queue auto pipeline when linked jobs reach a terminal state."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import JobStatus, JobType, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.models.reup_queue import ReupQueueItem
from src.services.reup_pipeline_meta import (
    ANALYZE_AUDIO_JOB_ID_KEY,
    AUTO_PIPELINE_MODES,
    OCR_JOB_ID_KEY,
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_MODE_AUTO_TO_TTS,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_KEY,
    PIPELINE_STEP_DOWNLOAD,
    PIPELINE_STEP_NEEDS_ATTENTION,
    PIPELINE_STEP_OCR,
    PIPELINE_STEP_QUALITY_REVIEW,
    PIPELINE_STEP_READY_FINAL,
    PIPELINE_STEP_RENDER,
    PIPELINE_STEP_TRANSLATE,
    PIPELINE_STEP_TRANSLATION_REVIEW,
    PIPELINE_STEP_TTS,
    RENDER_JOB_ID_KEY,
    RENDER_QA_KEY,
    QUALITY_WORKFLOW_STAGE_KEY,
    TRANSLATION_JOB_ID_KEY,
    TTS_JOB_ID_KEY,
    DOWNLOAD_JOB_ID_KEY,
    get_last_completed_step,
    get_pipeline_mode,
    get_pipeline_step,
    is_auto_pipeline,
    is_pipeline_held,
    meta_dict,
    set_pipeline_meta,
)
from src.services.reup_pipeline_plan import PIPELINE_STEP_ORDER, next_pipeline_step

logger = logging.getLogger(__name__)

_ACTIVE_QUEUE_STATUSES = (
    ReupQueueStatus.READY_FOR_PROCESSING,
    ReupQueueStatus.WAITING_FOR_MEDIA,
    ReupQueueStatus.WAITING_FOR_METADATA,
    ReupQueueStatus.PROCESSING,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReupPipelineOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    def on_job_terminal(self, job: Any) -> int:
        """Advance auto-pipeline items linked to a terminal job. Returns updated count."""
        status = _status_value(getattr(job, "status", None))
        if status not in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            return 0

        items = self._find_items_for_job(job)
        if not items:
            return 0

        completed_step = _COMPLETED_STEP_BY_JOB_TYPE.get(_type_value(getattr(job, "job_type", None)))
        recorded = False
        updated = 0
        for item in items:
            if status == JobStatus.COMPLETED.value and completed_step is not None:
                # Record progress for manual items too, so switching them to auto later
                # resumes from what actually finished.
                recorded = self._record_completed_step(item, completed_step) or recorded
            if not is_auto_pipeline(item):
                continue
            if status == JobStatus.FAILED.value:
                # The preview worker deliberately fails closed when encoded
                # Output QA finds residual CJK.  Treat that terminal job as a
                # recoverable quality signal in the full-auto lane instead of
                # converting it into a dead-end operator error.  The summary is
                # hash-bound to the failed preview and exposes only current
                # encoded residual evidence.
                if (
                    _type_value(getattr(job, "job_type", None))
                    == JobType.RENDER_PREVIEW.value
                    and get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER
                    and get_pipeline_step(item) == PIPELINE_STEP_QUALITY_REVIEW
                ):
                    from src.services.quality_localization_service import (
                        QualityLocalizationService,
                    )

                    summary = QualityLocalizationService(self.db).summary(
                        item.source_video_id
                    )
                    if (
                        str(summary.get("workflow_stage") or "")
                        == "WAITING_RESIDUAL_TRIAGE"
                        and bool(summary.get("encoded_output_qa_current"))
                    ):
                        self._ensure_auto_residual_remediation(item)
                        updated += 1
                        continue
                self._mark_needs_attention(
                    item,
                    error_code=getattr(job, "error_code", None) or "PIPELINE_JOB_FAILED",
                    error_message=getattr(job, "error_message", None) or "Pipeline job failed.",
                )
                updated += 1
                continue
            if status == JobStatus.CANCELLED.value:
                # A queue Hold/CANCEL changes the item out of the active statuses
                # (or marks it held). If an operator cancelled the linked job from
                # Ops instead, fail closed here so the auto lane cannot be occupied
                # forever by a live-looking queue item.
                if not is_pipeline_held(item):
                    self._mark_needs_attention(
                        item,
                        error_code="PIPELINE_JOB_CANCELLED",
                        error_message="The linked pipeline job was cancelled outside the queue workflow.",
                    )
                    updated += 1
                continue
            if is_pipeline_held(item):
                logger.info(
                    "reup_pipeline_hold_blocks_advance",
                    extra={"reup_queue_item_id": str(item.id), "job_id": str(getattr(job, "id", ""))},
                )
                continue
            if (
                status == JobStatus.COMPLETED.value
                and _type_value(getattr(job, "job_type", None))
                == JobType.RENDER_PREVIEW.value
                and get_pipeline_step(item) == PIPELINE_STEP_QUALITY_REVIEW
            ):
                from src.services.quality_localization_service import (
                    QualityLocalizationService,
                )

                summary = QualityLocalizationService(self.db).summary(
                    item.source_video_id
                )
                if (
                    get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER
                    and bool(summary.get("can_render_final"))
                ):
                    set_pipeline_meta(item, step=PIPELINE_STEP_RENDER)
                    self._ensure_render(item)
                elif get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER:
                    if str(summary.get("workflow_stage") or "") == "WAITING_RESIDUAL_TRIAGE":
                        self._ensure_auto_residual_remediation(item)
                    else:
                        self._mark_needs_attention(
                            item,
                            error_code="AUTO_QUALITY_GATE_BLOCKED",
                            error_message=(
                                "Full-auto quality policy stopped at "
                                f"{summary.get('workflow_stage') or 'UNKNOWN'}; "
                                "the artifact did not satisfy deterministic approval rules."
                            ),
                        )
                else:
                    self._park_for_quality_review(item, summary=summary)
                updated += 1
                continue
            if self._advance_after_success(item, job):
                updated += 1

        if updated or recorded:
            self.db.flush()
        # A finished or failed clip may have just freed a slot in the lane.
        workspace_id = getattr(job, "workspace_id", None) or getattr(items[0], "workspace_id", None)
        if workspace_id is not None:
            try:
                self.admit_waiting_items(workspace_id=workspace_id)
            except Exception:  # noqa: BLE001 — admission must never undo a completed job
                logger.exception(
                    "reup_pipeline_admit_after_terminal_failed",
                    extra={"job_id": str(getattr(job, "id", ""))},
                )
        if updated:
            logger.info(
                "reup_pipeline_advanced",
                extra={
                    "job_id": str(getattr(job, "id", "")),
                    "job_type": str(getattr(job, "job_type", "")),
                    "updated_count": updated,
                },
            )
        return updated

    def admit_waiting_items(self, *, workspace_id: Any) -> int:
        """Start parked auto items while the lane has room. Returns how many started."""
        from src.core.settings import get_settings
        from src.services.reup_pipeline_admission import (
            admission_plan,
            clear_slot_wait,
            max_items_in_flight,
        )

        limit = max_items_in_flight(get_settings())
        candidates = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.workspace_id == workspace_id,
                    ReupQueueItem.status.in_(_ACTIVE_QUEUE_STATUSES),
                )
            ).all()
        )
        self.reconcile_stale_auto_items(candidates)
        admitted = 0
        for item in admission_plan(candidates, limit=limit):
            try:
                clear_slot_wait(item)
                mode = get_pipeline_mode(item)
                self.set_automation(item, mode=mode)
            except Exception:  # noqa: BLE001 — one bad clip must not stall the lane
                logger.exception(
                    "reup_pipeline_admission_failed",
                    extra={"reup_queue_item_id": str(getattr(item, "id", ""))},
                )
                continue
            item.last_action_note = "Auto pipeline: slot free — pipeline resumed."
            admitted += 1
        if admitted:
            logger.info(
                "reup_pipeline_items_admitted",
                extra={"workspace_id": str(workspace_id), "admitted": admitted, "limit": limit},
            )
            self.db.flush()
        return admitted

    def reconcile_stale_auto_items(self, candidates: list[ReupQueueItem]) -> int:
        """Repair terminal/missing stage links before counting auto-lane slots.

        Queue state can outlive a job row when an operator cancels from Ops, a
        database restore removes an old job, or a worker crashes between creating
        a stage job and persisting its metadata. Such rows must not consume one of
        the bounded auto slots indefinitely. Completed jobs are advanced; missing
        jobs are recreated idempotently; failed/cancelled jobs become explicit
        operator attention instead of silently looping.
        """
        from src.models.jobs import Job

        repaired = 0
        step_job_keys = {
            PIPELINE_STEP_DOWNLOAD: DOWNLOAD_JOB_ID_KEY,
            PIPELINE_STEP_ANALYZE_AUDIO: ANALYZE_AUDIO_JOB_ID_KEY,
            PIPELINE_STEP_TRANSLATE: TRANSLATION_JOB_ID_KEY,
            PIPELINE_STEP_TTS: TTS_JOB_ID_KEY,
            PIPELINE_STEP_OCR: OCR_JOB_ID_KEY,
            PIPELINE_STEP_RENDER: RENDER_JOB_ID_KEY,
        }
        for item in candidates:
            if not is_auto_pipeline(item) or is_pipeline_held(item):
                continue
            if meta_dict(item).get("pipeline_awaiting_slot"):
                continue
            step = get_pipeline_step(item)
            if step not in _ENSURE_METHOD_BY_STEP:
                continue
            meta = meta_dict(item)
            # Reconcile only a stage-specific authority id. ``item.job_id`` is
            # intentionally not enough here: during a normal terminal callback
            # it still points at the just-completed prior job while the next
            # stage is being enqueued.
            stage_job_key = step_job_keys.get(step)
            raw_job_id = meta.get(stage_job_key) if stage_job_key else None
            if not raw_job_id and step == PIPELINE_STEP_DOWNLOAD:
                raw_job_id = getattr(item, "job_id", None)
            if not raw_job_id:
                # Do not infer a missing download job for synthetic/test rows;
                # production rows created by the orchestrator always persist an
                # item.job_id or a stage-specific metadata id.
                continue
            try:
                job_id = raw_job_id if isinstance(raw_job_id, UUID) else UUID(str(raw_job_id))
                job = self.db.get(Job, job_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "reup_pipeline_stale_job_lookup_failed",
                    extra={"reup_queue_item_id": str(item.id)},
                )
                continue
            if job is None:
                item.job_id = None
                try:
                    self._ensure_step(step, item)
                    item.last_action_note = f"Auto pipeline recovered a missing {step} job."
                    repaired += 1
                except Exception as exc:  # noqa: BLE001
                    self._mark_needs_attention(
                        item,
                        error_code="PIPELINE_JOB_MISSING",
                        error_message=f"The {step} job is missing and could not be recreated: {exc}",
                    )
                continue
            status = _status_value(getattr(job, "status", None))
            if status == JobStatus.COMPLETED.value:
                completed_step = _COMPLETED_STEP_BY_JOB_TYPE.get(_type_value(getattr(job, "job_type", None)))
                if completed_step == step and self._advance_after_success(item, job):
                    repaired += 1
                continue
            if status in {JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                self._mark_needs_attention(
                    item,
                    error_code=getattr(job, "error_code", None) or "PIPELINE_JOB_TERMINAL",
                    error_message=(
                        getattr(job, "error_message", None)
                        or f"The linked {step} job is {status.lower()} and needs review."
                    ),
                )
                repaired += 1
        if repaired:
            self.db.flush()
        return repaired

    def resume_item(self, item: ReupQueueItem) -> ReupQueueItem:
        """Clear hold and re-enqueue the step the item was paused on."""
        set_pipeline_meta(item, hold=False)
        item.held_at = None
        step = meta_dict(item).get("pipeline_step") or PIPELINE_STEP_DOWNLOAD
        if get_pipeline_mode(item) not in AUTO_PIPELINE_MODES:
            set_pipeline_meta(item, mode=PIPELINE_MODE_AUTO_TO_TTS)
        if step == PIPELINE_STEP_NEEDS_ATTENTION:
            # A quality gate can fail after its durable job technically
            # completed. Resume the failed authority stage from its cache,
            # rather than resetting the whole auto lane to Download.
            last_completed = get_last_completed_step(item)
            if (
                last_completed == PIPELINE_STEP_ANALYZE_AUDIO
                and not self._dialogue_is_uncertain(item)
            ):
                # The operator resolved low-confidence dialogue in Transcript.
                # Continue from the approved Analyze output; re-running ASR here
                # would discard the reviewed authority and can recreate the same gate.
                self.set_automation(item, mode=get_pipeline_mode(item))
                return item
            if last_completed in {
                PIPELINE_STEP_ANALYZE_AUDIO,
                PIPELINE_STEP_TRANSLATE,
                PIPELINE_STEP_TTS,
                PIPELINE_STEP_OCR,
                PIPELINE_STEP_RENDER,
            }:
                step = last_completed
                set_pipeline_meta(item, step=step)
            else:
                return item
        if step in {
            PIPELINE_STEP_READY_FINAL,
            PIPELINE_STEP_TRANSLATION_REVIEW,
        }:
            return item
        self._ensure_step(step, item)
        return item

    def resume_quality_approved_items(self, *, source_video_id: UUID) -> int:
        """Resume auto-to-render items after the explicit visual approval gate."""

        items = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.source_video_id == source_video_id,
                    ReupQueueItem.status.in_(_ACTIVE_QUEUE_STATUSES),
                )
            ).all()
        )
        resumed = 0
        for item in items:
            if (
                get_pipeline_mode(item) != PIPELINE_MODE_AUTO_TO_RENDER
                or get_pipeline_step(item) != PIPELINE_STEP_QUALITY_REVIEW
                or is_pipeline_held(item)
            ):
                continue
            set_pipeline_meta(item, step=PIPELINE_STEP_RENDER)
            if self._ensure_render(item):
                resumed += 1
        if resumed:
            self.db.flush()
        return resumed

    def resume_translation_approved_items(
        self, *, source_video_id: UUID
    ) -> tuple[int, UUID | None]:
        """Resume recipe-bound TTS after the frontend translation checkpoint."""

        items = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.source_video_id == source_video_id,
                    ReupQueueItem.status.in_(_ACTIVE_QUEUE_STATUSES),
                )
            ).all()
        )
        resumed = 0
        job_id: UUID | None = None
        for item in items:
            if (
                not is_auto_pipeline(item)
                or get_pipeline_step(item) != PIPELINE_STEP_TRANSLATION_REVIEW
                or is_pipeline_held(item)
            ):
                continue
            set_pipeline_meta(item, step=PIPELINE_STEP_TTS)
            if self._ensure_tts(item):
                resumed += 1
                job_id = item.job_id
        if resumed:
            self.db.flush()
        return resumed, job_id

    def set_automation(self, item: ReupQueueItem, *, mode: str) -> str | None:
        """Switch automation level in place. Returns the step it kicked off, if any.

        Nothing is re-run: an item with a live job keeps it and the new stop point applies
        when that job finishes, and an idle item continues from the step it last completed.
        """
        if mode not in AUTO_PIPELINE_MODES:
            set_pipeline_meta(item, mode=mode)
            return None

        set_pipeline_meta(item, mode=mode, hold=False)
        item.held_at = None
        if self._has_live_job(item):
            return None

        last_done = get_last_completed_step(item)
        pinned_step = meta_dict(item).get(PIPELINE_STEP_KEY)
        if last_done == PIPELINE_STEP_ANALYZE_AUDIO and self._dialogue_is_uncertain(item):
            self._mark_needs_attention(
                item,
                error_code="DIALOGUE_DETECTION_UNCERTAIN",
                error_message=(
                    "Speech was detected, but the transcript quality contract requires review. "
                    "Review or re-run Analyze Audio before translation."
                ),
            )
            return None
        if last_done is None and pinned_step in PIPELINE_STEP_ORDER:
            # No recorded progress (older item, or interrupted before finishing anything):
            # the pinned step is the safest place to pick up.
            self._ensure_step(pinned_step, item)
            return pinned_step

        next_step = next_pipeline_step(
            current_step=last_done,
            mode=mode,
            skip_dubbing=self._should_skip_dubbing(item),
        )
        if next_step is None:
            self._finish_pipeline(item, mode=mode, skip_dubbing=self._should_skip_dubbing(item))
            return None
        set_pipeline_meta(item, step=next_step)
        self._ensure_step(next_step, item)
        return next_step

    def _has_live_job(self, item: ReupQueueItem) -> bool:
        job_id = getattr(item, "job_id", None)
        if job_id is None:
            return False
        from src.models.jobs import Job

        job = self.db.get(Job, job_id)
        if job is None:
            return False
        return _status_value(getattr(job, "status", None)) not in {
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }

    def _ensure_step(self, step: str, item: ReupQueueItem) -> bool:
        from src.services.pipeline_recipe_runtime import (
            RuntimeRecipeError,
            ensure_item_recipe_binding,
        )

        try:
            ensure_item_recipe_binding(item)
        except RuntimeRecipeError as exc:
            self._mark_needs_attention(
                item,
                error_code="PIPELINE_RECIPE_INVALID",
                error_message=str(exc),
            )
            return True
        method = _ENSURE_METHOD_BY_STEP.get(step, "_ensure_download")
        ensured = bool(getattr(self, method)(item))
        if ensured:
            self._catch_up_terminal_step(step, item)
        return ensured

    def _catch_up_terminal_step(self, step: str, item: ReupQueueItem) -> bool:
        """Consume a terminal job that finished before its queue binding was observed."""
        from src.models.jobs import Job

        job_id = getattr(item, "job_id", None)
        if job_id is None:
            return False
        job = self.db.get(Job, job_id)
        if job is None:
            return False
        completed_step = _COMPLETED_STEP_BY_JOB_TYPE.get(
            _type_value(getattr(job, "job_type", None))
        )
        if completed_step != step:
            return False
        status = _status_value(getattr(job, "status", None))
        if status == JobStatus.COMPLETED.value:
            self._record_completed_step(item, completed_step)
            return self._advance_after_success(item, job)
        if status in {JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            self._mark_needs_attention(
                item,
                error_code=getattr(job, "error_code", None) or "PIPELINE_JOB_TERMINAL",
                error_message=(
                    getattr(job, "error_message", None)
                    or f"The linked {step} job is {status.lower()} and needs review."
                ),
            )
            return True
        return False

    def _record_completed_step(self, item: ReupQueueItem, completed_step: str) -> bool:
        """Record progress monotonically so a delayed old callback cannot rewind it."""
        if completed_step not in PIPELINE_STEP_ORDER:
            return False
        current = get_last_completed_step(item)
        if current in PIPELINE_STEP_ORDER and (
            PIPELINE_STEP_ORDER.index(current) > PIPELINE_STEP_ORDER.index(completed_step)
        ):
            return False
        if current == completed_step:
            return False
        set_pipeline_meta(item, last_completed_step=completed_step)
        return True

    def _bind_job_recipe(self, item: ReupQueueItem, job_id: Any) -> bool:
        """Attach the immutable item recipe to a durable stage job."""

        from src.models.jobs import Job
        from src.services.pipeline_recipe_runtime import (
            RuntimeRecipeError,
            bind_job_to_item_recipe,
        )

        job = self.db.get(Job, job_id)
        if job is None:
            # Some legacy/test adapters return only the submitted id and make the
            # row visible after this transaction.  The item already carries the
            # immutable authority; a later runner/terminal callback will still
            # require a real durable job before it can advance.
            logger.warning(
                "reup_pipeline_recipe_job_binding_deferred",
                extra={
                    "reup_queue_item_id": str(getattr(item, "id", "")),
                    "job_id": str(job_id),
                },
            )
            return True
        try:
            bind_job_to_item_recipe(job, item)
        except RuntimeRecipeError as exc:
            self._mark_needs_attention(
                item,
                error_code="PIPELINE_RECIPE_INVALID",
                error_message=str(exc),
            )
            return False
        return True

    def _advance_after_success(self, item: ReupQueueItem, job: Any) -> bool:
        job_type = _type_value(getattr(job, "job_type", None))
        completed_step = _COMPLETED_STEP_BY_JOB_TYPE.get(job_type)
        if completed_step is None:
            return False

        current_step = get_pipeline_step(item)
        if current_step != completed_step:
            # Delayed completion from an earlier stage may update monotonic
            # history, but it must never skip or rewind the current stage.
            logger.info(
                "reup_pipeline_stale_terminal_ignored",
                extra={
                    "reup_queue_item_id": str(getattr(item, "id", "")),
                    "job_id": str(getattr(job, "id", "")),
                    "completed_step": completed_step,
                    "current_step": current_step,
                },
            )
            return False

        if completed_step == PIPELINE_STEP_ANALYZE_AUDIO and self._dialogue_is_uncertain(item):
            # VAD measured speech the ASR could not decode: guessing either way here
            # either drops needed dubbing or dubs silence, so hand it to an operator.
            self._mark_needs_attention(
                item,
                error_code="DIALOGUE_DETECTION_UNCERTAIN",
                error_message=(
                    "Speech detected in the audio but transcription produced no dialogue. "
                    "Review the clip, then re-run analyze or mark it as no dialogue."
                ),
            )
            return True

        if completed_step == PIPELINE_STEP_OCR:
            payload = dict(getattr(job, "payload_json", None) or {})
            if payload.get("workflow_version") == "QUALITY_LOCALIZATION_V24_1":
                from src.services.quality_localization_service import QualityLocalizationService

                summary = QualityLocalizationService(self.db).summary(item.source_video_id)
                if get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER:
                    stage = str(summary.get("workflow_stage") or "UNKNOWN")
                    if bool(summary.get("can_render_final")):
                        set_pipeline_meta(item, step=PIPELINE_STEP_RENDER)
                        return self._ensure_render(item)
                    if stage == "WAITING_OCR_REVIEW":
                        return self._ensure_auto_ocr_review(item, summary=summary)
                    if stage in {
                        "WAITING_TRANSLATION_REVIEW",
                        "READY_FOR_VISUAL_PREVIEW",
                        # OCR can be resumed after a Phase 4 contract fix while
                        # the independent TTS/audio handoff is already
                        # approved. Rebuild only the visual preview authority;
                        # do not force Download/ASR/Translation/TTS to run.
                        "AUDIO_APPROVED",
                    }:
                        return self._ensure_quality_preview(item, summary=summary)
                    self._mark_needs_attention(
                        item,
                        error_code="AUTO_QUALITY_GATE_BLOCKED",
                        error_message=(
                            f"Full-auto quality policy stopped at {stage}; "
                            "the artifact did not satisfy deterministic approval rules."
                        ),
                    )
                    return True
                if not bool(summary.get("can_render_final")):
                    self._park_for_quality_review(item, summary=summary)
                    return True

        if completed_step == PIPELINE_STEP_RENDER:
            # Last stage of full auto: nobody watched the intermediate steps, so grade the
            # output here instead of letting a truncated or mute render reach review unmarked.
            # Same chokepoint stamps the recipe fingerprint — every finished product passes here.
            from src.services.pipeline_recipe import stamp_pipeline_recipe

            stamp_pipeline_recipe(
                item,
                pipeline_mode=get_pipeline_mode(item),
                skip_dubbing=self._should_skip_dubbing(item),
            )
            verdict = self._render_qa_verdict(item)
            if verdict is not None:
                set_pipeline_meta(item, extra={RENDER_QA_KEY: verdict.to_dict()})
                if not verdict.can_auto_finish:
                    self._mark_needs_attention(
                        item,
                        error_code="RENDER_QA_FAILED",
                        error_message=verdict.summary,
                    )
                    return True
                # In the explicit full-auto lane, a deterministic PASS is the
                # final quality gate.  Promote the already persisted adaptive
                # RenderOutput to publish-ready and create the local Phase-5
                # package boundary.  Metadata/rights/manual upload remain
                # explicit handoff gates; no external publish is triggered.
                if (
                    get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER
                    and str(verdict.status) == "pass"
                    and self._auto_finalize_quality_render(item, job)
                ):
                    return True

        advanced = self._run_next_step(item, completed_step=completed_step)
        if completed_step == PIPELINE_STEP_RENDER and advanced:
            qa = meta_dict(item).get(RENDER_QA_KEY) or {}
            if qa.get("status") == "warn":
                item.last_action_note = f"Auto pipeline: render complete — QA warning: {qa.get('summary', '')}"[:500]
        return advanced

    def _auto_finalize_quality_render(self, item: ReupQueueItem, job: Any) -> bool:
        """Finalize a deterministic quality render for the auto-to-render lane."""

        payload = dict(getattr(job, "payload_json", None) or {})
        if str(payload.get("workflow_version") or "") != "QUALITY_LOCALIZATION_V24_1":
            return False
        from src.models.media import RenderOutput
        from src.render_pipeline.services.render_service import RenderService

        render = self.db.scalar(
            select(RenderOutput)
            .where(
                RenderOutput.source_video_id == item.source_video_id,
                RenderOutput.created_by_job_id == getattr(job, "id", None),
            )
            .order_by(RenderOutput.version.desc())
            .limit(1)
        )
        if render is None:
            self._mark_needs_attention(
                item,
                error_code="AUTO_FINAL_RENDER_OUTPUT_MISSING",
                error_message="Final render passed QA but its RenderOutput record is missing.",
            )
            return True
        try:
            RenderService(self.db).mark_publish_ready(render.id)
        except Exception as exc:  # noqa: BLE001
            self._mark_needs_attention(
                item,
                error_code="AUTO_FINAL_HANDOFF_FAILED",
                error_message=f"Final render passed QA but local handoff failed: {exc}",
            )
            return True
        item.render_output_id = render.id
        item.job_id = getattr(job, "id", None)
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_READY_FINAL,
            extra={
                QUALITY_WORKFLOW_STAGE_KEY: "FINAL_READY",
                "quality_auto_finalized": True,
                "quality_auto_finalized_at": utc_now().isoformat(),
            },
        )
        item.last_action_note = (
            "Full auto: final QA PASS; local Final Approval and export package boundary created. "
            "Metadata, rights/music, and manual upload remain operator handoff gates."
        )
        return True

    def _render_qa_verdict(self, item: ReupQueueItem) -> Any:
        from src.services import render_qa_gate

        try:
            metrics = render_qa_gate.collect_render_qa_metrics(
                self.db,
                getattr(item, "source_video_id", None),
                dub_expected=not self._should_skip_dubbing(item),
            )
            if metrics is None:
                return None
            return render_qa_gate.evaluate_render_qa(metrics)
        except Exception:  # noqa: BLE001 — a QA defect must never strand a finished render
            logger.exception(
                "reup_pipeline_render_qa_failed",
                extra={"reup_queue_item_id": str(getattr(item, "id", ""))},
            )
            return None

    def _run_next_step(self, item: ReupQueueItem, *, completed_step: str | None) -> bool:
        mode = get_pipeline_mode(item)
        skip_dubbing = self._should_skip_dubbing(item)
        next_step = next_pipeline_step(
            current_step=completed_step, mode=mode, skip_dubbing=skip_dubbing
        )
        if next_step is None:
            return self._finish_pipeline(item, mode=mode, skip_dubbing=skip_dubbing)

        set_pipeline_meta(item, step=next_step)
        return bool(self._ensure_step(next_step, item))

    def _finish_pipeline(self, item: ReupQueueItem, *, mode: str, skip_dubbing: bool) -> bool:
        set_pipeline_meta(item, step=PIPELINE_STEP_READY_FINAL)
        if mode == PIPELINE_MODE_AUTO_TO_RENDER:
            note = "Auto pipeline: render complete — compare and approve in Final Review."
        elif skip_dubbing:
            note = "Auto pipeline: no dialogue — ready for Final Review (OCR/Render)."
        else:
            note = "Auto pipeline: TTS complete — open Final Review for OCR/Render."
        item.last_action_note = note
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        return True

    def _ensure_download(self, item: ReupQueueItem) -> bool:
        from src.downloaders.errors import DownloadError
        from src.services.reup_queue_service import ReupQueueService

        svc = ReupQueueService(self.db)
        try:
            item.job_id = svc._ensure_download_job_id(item)
        except DownloadError as exc:
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True

        if not self._bind_job_recipe(item, item.job_id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_DOWNLOAD,
            extra={DOWNLOAD_JOB_ID_KEY: str(item.job_id)},
        )
        item.status = ReupQueueStatus.WAITING_FOR_MEDIA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA
        item.started_at = item.started_at or utc_now()
        return True

    def _ensure_analyze_audio(self, item: ReupQueueItem) -> bool:
        from src.audio_pipeline.errors import AudioAnalysisError
        from src.services.reup_queue_service import ReupQueueService

        svc = ReupQueueService(self.db)
        now = utc_now()
        item.media_ready_at = item.media_ready_at or now
        # Clear prior download job link so ensure-analyze can create/reuse analyze job.
        prior = item.job_id
        item.job_id = None
        try:
            item.job_id = svc._ensure_analyze_audio_job_id(item)
        except AudioAnalysisError as exc:
            if prior is not None:
                item.job_id = prior
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True
        if not self._bind_job_recipe(item, item.job_id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_ANALYZE_AUDIO,
            extra={ANALYZE_AUDIO_JOB_ID_KEY: str(item.job_id)},
        )
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = "Auto pipeline: analyze audio enqueued."
        return True

    def _ensure_translation(self, item: ReupQueueItem) -> bool:
        from src.audio_pipeline.errors import AudioAnalysisError
        from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
        from src.audio_pipeline.types import TranslationPreset

        try:
            job = AudioAnalysisService(self.db).create_translation_job(
                item.source_video_id,
                translation_preset=TranslationPreset.LITERAL_SAFE,
                force_refresh=False,
                require_source_approved=False,
                idempotency_key=f"reup-queue:{item.id}:translate",
                commit=False,
            )
        except AudioAnalysisError as exc:
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_TRANSLATE,
            extra={TRANSLATION_JOB_ID_KEY: str(job.id)},
        )
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = "Auto pipeline: translation draft enqueued."
        return True

    def _ensure_tts(self, item: ReupQueueItem) -> bool:
        from src.tts_pipeline.errors import TtsPipelineError
        from src.tts_pipeline.services.tts_service import TtsPipelineService
        from src.tts_pipeline.types import TtsRequest

        try:
            job = TtsPipelineService(self.db).create_tts_job(
                TtsRequest(
                    source_video_id=item.source_video_id,
                    force_refresh=False,
                ),
                commit=False,
            )
        except TtsPipelineError as exc:
            if str(exc.code) == "translation_review_required":
                self._park_for_translation_review(item, message=exc.message)
                return True
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True
        except Exception as exc:  # noqa: BLE001 — surface unexpected TTS create failures as needs attention
            self._mark_needs_attention(
                item,
                error_code="TTS_CREATE_FAILED",
                error_message=str(exc) or "Failed to create TTS job.",
            )
            return True
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(item, step=PIPELINE_STEP_TTS, extra={TTS_JOB_ID_KEY: str(job.id)})
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = "Auto pipeline: TTS enqueued."
        return True

    def _ensure_ocr(self, item: ReupQueueItem) -> bool:
        from src.ocr_pipeline.errors import OcrPipelineError
        from src.ocr_pipeline.services.ocr_service import OcrPipelineService
        from src.ocr_pipeline.types import OcrRequest
        from src.services.quality_localization_service import QUALITY_WORKFLOW_VERSION
        from src.services.quality_localization_service import QUALITY_ANALYSIS_ENGINE

        try:
            job = OcrPipelineService(self.db).create_ocr_job(
                OcrRequest(
                    source_video_id=item.source_video_id,
                    force_refresh=False,
                    clean_hardsub=True,
                    use_master_phase1=True,
                    workflow_version=QUALITY_WORKFLOW_VERSION,
                    analysis_engine=QUALITY_ANALYSIS_ENGINE,
                    auto_advance=(
                        get_pipeline_mode(item) == PIPELINE_MODE_AUTO_TO_RENDER
                    ),
                ),
                commit=False,
            )
        except OcrPipelineError as exc:
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True
        except Exception as exc:  # noqa: BLE001
            self._mark_needs_attention(
                item,
                error_code="OCR_CREATE_FAILED",
                error_message=str(exc) or "Failed to create OCR job.",
            )
            return True
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(item, step=PIPELINE_STEP_OCR, extra={OCR_JOB_ID_KEY: str(job.id)})
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = "Auto pipeline: OCR enqueued."
        return True

    def _ensure_auto_ocr_review(
        self, item: ReupQueueItem, *, summary: dict[str, Any]
    ) -> bool:
        """Resume a pre-policy OCR run with deterministic provenance decisions."""

        from src.ocr_pipeline.services.ocr_service import OcrPipelineService
        from src.ocr_pipeline.types import OcrRequest
        from src.services.quality_auto_policy import (
            AUTO_QUALITY_ACTOR,
            QualityAutoPolicyBlocked,
            build_ocr_decisions,
        )
        from src.services.quality_localization_service import (
            QUALITY_ANALYSIS_ENGINE,
            QUALITY_WORKFLOW_VERSION,
        )

        try:
            decisions = build_ocr_decisions(
                list(summary.get("review_objects") or [])
            )
        except QualityAutoPolicyBlocked as exc:
            self._mark_needs_attention(
                item,
                error_code="AUTO_OCR_DECISION_BLOCKED",
                error_message=str(exc),
            )
            return True
        job = OcrPipelineService(self.db).create_ocr_job(
            OcrRequest(
                source_video_id=item.source_video_id,
                force_refresh=False,
                clean_hardsub=False,
                use_master_phase1=True,
                workflow_version=QUALITY_WORKFLOW_VERSION,
                workflow_action="approve_ocr",
                review_decisions=decisions,
                operator_id=AUTO_QUALITY_ACTOR,
                analysis_engine=QUALITY_ANALYSIS_ENGINE,
                auto_advance=True,
            ),
            commit=False,
        )
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_OCR,
            extra={OCR_JOB_ID_KEY: str(job.id)},
        )
        item.last_action_note = "Full auto: deterministic OCR review enqueued."
        return True

    def _ensure_quality_preview(
        self, item: ReupQueueItem, *, summary: dict[str, Any]
    ) -> bool:
        from src.services.quality_auto_policy import (
            AUTO_QUALITY_ACTOR,
            QualityAutoPolicyBlocked,
            build_translation_decisions,
        )
        from src.services.quality_localization_service import QualityLocalizationService

        translations: list[dict[str, str]] | None
        if str(summary.get("workflow_stage") or "") == "READY_FOR_VISUAL_PREVIEW":
            translations = None
        else:
            try:
                translations = build_translation_decisions(
                    list(summary.get("translation_objects") or [])
                )
            except QualityAutoPolicyBlocked as exc:
                self._mark_needs_attention(
                    item,
                    error_code="AUTO_TRANSLATION_DECISION_BLOCKED",
                    error_message=str(exc),
                )
                return True
        job = QualityLocalizationService(self.db).create_preview_job(
            item.source_video_id,
            translations=translations,
            operator_id=AUTO_QUALITY_ACTOR,
            auto_approve=True,
        )
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_QUALITY_REVIEW,
            extra={QUALITY_WORKFLOW_STAGE_KEY: "AUTO_PREVIEW_QUEUED"},
        )
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = (
            "Full auto: translation, visual QA, and audio QA preview enqueued."
        )
        return True

    def _ensure_auto_residual_remediation(
        self,
        item: ReupQueueItem,
        *,
        summary: dict[str, Any] | None = None,
    ) -> bool:
        from src.services.quality_auto_policy import AUTO_QUALITY_ACTOR
        from src.services.quality_localization_service import QualityLocalizationService

        meta = meta_dict(item)
        current_summary = summary or QualityLocalizationService(self.db).summary(
            item.source_video_id
        )
        authority = str(current_summary.get("residual_authority_source") or "")
        attempts_key = (
            "quality_auto_output_residual_attempts"
            if authority == "encoded_visual_preview_output_qa"
            else "quality_auto_preflight_residual_attempts"
        )
        authority_sha = str(current_summary.get("residual_authority_sha256") or "")
        authority_sha_key = f"{attempts_key}_authority_sha256"
        authority_revision_changed = bool(
            authority_sha and str(meta.get(authority_sha_key) or "") != authority_sha
        )
        if authority_revision_changed:
            attempts = 0
        elif attempts_key in meta:
            attempts = int(meta.get(attempts_key) or 0)
        elif authority == "encoded_visual_preview_output_qa":
            # Legacy total attempts were preflight-only.  Do not let them hide
            # a newly discovered post-encode residual.
            attempts = 0
        else:
            attempts = int(meta.get("quality_auto_residual_attempts") or 0)
        if attempts >= 2:
            self._mark_needs_attention(
                item,
                error_code="AUTO_RESIDUAL_REMEDIATION_EXHAUSTED",
                error_message=(
                    "Residual CJK remained after two hash-bound automatic remediation "
                    f"attempts for {authority or 'preflight'} authority."
                ),
            )
            return True
        job = QualityLocalizationService(self.db).create_residual_review_job(
            item.source_video_id,
            action="auto_residual_remediation",
            operator_id=AUTO_QUALITY_ACTOR,
            auto_approve=True,
        )
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_QUALITY_REVIEW,
            extra={
                QUALITY_WORKFLOW_STAGE_KEY: "AUTO_RESIDUAL_REMEDIATION_QUEUED",
                attempts_key: attempts + 1,
                authority_sha_key: authority_sha or None,
                "quality_auto_residual_attempts": int(
                    meta.get("quality_auto_residual_attempts") or 0
                )
                + 1,
                "quality_auto_residual_authority": authority or "phase4_preflight",
            },
        )
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.failed_at = None
        item.last_action_note = "Full auto: residual CJK remediation enqueued."
        item.last_error_code = None
        item.last_error_message = None
        return True

    def _ensure_render(self, item: ReupQueueItem) -> bool:
        from src.render_pipeline.errors import RenderPipelineError
        from src.render_pipeline.services.render_service import RenderService
        from src.render_pipeline.types import RenderRequest
        from src.services.quality_localization_service import QUALITY_WORKFLOW_VERSION

        try:
            job = RenderService(self.db).create_render_job(
                RenderRequest(
                    source_video_id=item.source_video_id,
                    force_refresh=True,
                    workflow_version=QUALITY_WORKFLOW_VERSION,
                ),
                commit=False,
            )
        except RenderPipelineError as exc:
            self._mark_needs_attention(item, error_code=str(exc.code), error_message=exc.message)
            return True
        except Exception as exc:  # noqa: BLE001
            self._mark_needs_attention(
                item,
                error_code="RENDER_CREATE_FAILED",
                error_message=str(exc) or "Failed to create render job.",
            )
            return True
        item.job_id = job.id
        if not self._bind_job_recipe(item, job.id):
            return True
        set_pipeline_meta(item, step=PIPELINE_STEP_RENDER, extra={RENDER_JOB_ID_KEY: str(job.id)})
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = "Auto pipeline: final render enqueued."
        return True

    def _park_for_quality_review(self, item: ReupQueueItem, *, summary: dict[str, Any]) -> None:
        stage = str(summary.get("workflow_stage") or "WAITING_QUALITY_REVIEW")
        set_pipeline_meta(
            item,
            step=PIPELINE_STEP_QUALITY_REVIEW,
            extra={QUALITY_WORKFLOW_STAGE_KEY: stage},
        )
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_action_note = f"Quality localization: {stage} — continue in Final Review."

    def _park_for_translation_review(self, item: ReupQueueItem, *, message: str) -> None:
        set_pipeline_meta(item, step=PIPELINE_STEP_TRANSLATION_REVIEW)
        item.job_id = None
        item.status = ReupQueueStatus.WAITING_FOR_METADATA
        item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
        item.last_error_code = "translation_review_required"
        item.last_error_message = str(
            message or "Vietnamese translation requires operator review"
        )
        item.last_action_note = (
            "Translation review required - open Transcript, correct/approve "
            "Vietnamese, then Generate TTS."
        )

    def _source_video_meta(self, item: ReupQueueItem) -> dict:
        source = getattr(item, "source_video", None)
        if source is None and getattr(item, "source_video_id", None) is not None:
            from src.models.ingestion import SourceVideo

            source = self.db.get(SourceVideo, item.source_video_id)
        meta = getattr(source, "metadata_json", None) or {}
        return meta if isinstance(meta, dict) else {}

    def _dialogue_is_uncertain(self, item: ReupQueueItem) -> bool:
        return self._source_video_meta(item).get("dialogue_phase") == "dialogue_uncertain"

    def _should_skip_dubbing(self, item: ReupQueueItem) -> bool:
        meta = self._source_video_meta(item)
        if meta.get("dialogue_phase") == "dialogue_uncertain":
            return False
        if meta.get("dialogue_phase") == "no_dialogue":
            return True
        if meta.get("has_speech") is False:
            return True
        flags = meta.get("difficulty_flags") or meta.get("flags_summary") or []
        if isinstance(flags, list) and "skip_dubbing" in flags:
            return True
        return False

    def _mark_needs_attention(self, item: ReupQueueItem, *, error_code: str, error_message: str) -> None:
        now = utc_now()
        item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
        item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
        item.failed_at = now
        item.blocked_at = now
        item.blocked_reason = error_message
        item.last_error_code = error_code
        item.last_error_message = error_message
        item.last_action_note = f"Auto pipeline stopped: {error_message}"
        set_pipeline_meta(item, step=PIPELINE_STEP_NEEDS_ATTENTION, hold=True)

    def _find_items_for_job(self, job: Any) -> list[ReupQueueItem]:
        job_id = getattr(job, "id", None)
        if job_id is None:
            return []
        by_job = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.job_id == job_id,
                    ReupQueueItem.status.in_(_ACTIVE_QUEUE_STATUSES),
                )
            ).unique()
        )
        if by_job:
            return by_job

        source_video_id = getattr(job, "source_video_id", None)
        if source_video_id is None:
            return []
        job_id_str = str(job_id)
        candidates = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.source_video_id == source_video_id,
                    ReupQueueItem.status.in_(_ACTIVE_QUEUE_STATUSES),
                )
            ).unique()
        )
        matched: list[ReupQueueItem] = []
        for item in candidates:
            if not is_auto_pipeline(item):
                continue
            meta = meta_dict(item)
            linked_ids = {
                str(meta.get(DOWNLOAD_JOB_ID_KEY) or ""),
                str(meta.get(ANALYZE_AUDIO_JOB_ID_KEY) or ""),
                str(meta.get(TRANSLATION_JOB_ID_KEY) or ""),
                str(meta.get(TTS_JOB_ID_KEY) or ""),
                str(meta.get(OCR_JOB_ID_KEY) or ""),
                str(meta.get(RENDER_JOB_ID_KEY) or ""),
            }
            quality_preview_match = (
                _type_value(getattr(job, "job_type", None))
                == JobType.RENDER_PREVIEW.value
                and get_pipeline_step(item) == PIPELINE_STEP_QUALITY_REVIEW
            )
            if (
                job_id_str in linked_ids
                or str(item.job_id) == job_id_str
                or quality_preview_match
            ):
                matched.append(item)
        return matched


_COMPLETED_STEP_BY_JOB_TYPE: dict[str, str] = {
    JobType.DOWNLOAD_VIDEO.value: PIPELINE_STEP_DOWNLOAD,
    JobType.ANALYZE_AUDIO.value: PIPELINE_STEP_ANALYZE_AUDIO,
    JobType.BUILD_TRANSLATION_DRAFT.value: PIPELINE_STEP_TRANSLATE,
    JobType.SYNTHESIZE_TTS.value: PIPELINE_STEP_TTS,
    JobType.ANALYZE_OCR.value: PIPELINE_STEP_OCR,
    JobType.RENDER_FINAL.value: PIPELINE_STEP_RENDER,
}

_ENSURE_METHOD_BY_STEP: dict[str, str] = {
    PIPELINE_STEP_DOWNLOAD: "_ensure_download",
    PIPELINE_STEP_ANALYZE_AUDIO: "_ensure_analyze_audio",
    PIPELINE_STEP_TRANSLATE: "_ensure_translation",
    PIPELINE_STEP_TTS: "_ensure_tts",
    PIPELINE_STEP_OCR: "_ensure_ocr",
    PIPELINE_STEP_RENDER: "_ensure_render",
}


def _status_value(raw: Any) -> str:
    if raw is None:
        return ""
    return raw.value if hasattr(raw, "value") else str(raw)


def _type_value(raw: Any) -> str:
    if raw is None:
        return ""
    return raw.value if hasattr(raw, "value") else str(raw)
