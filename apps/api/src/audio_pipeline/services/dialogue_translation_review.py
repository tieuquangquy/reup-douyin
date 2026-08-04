"""Hash-bound operator review artifact for dialogue translation before TTS."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.audio_pipeline.speech_budget import assess_speech_budget
from src.audio_pipeline.services.transcript_edit_service import (
    SegmentEdit,
    TranscriptEditService,
)
from src.enums import TranscriptSegmentStatus
from src.models.artifacts import TranslationSegment


SCHEMA_VERSION = "dialogue_translation_review_v1"
APPROVAL_SCHEMA_VERSION = "dialogue_translation_approval_v1"


class DialogueTranslationReviewError(RuntimeError):
    pass


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _transcript_authority(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source_video_id": str(row.source_video_id),
        "segment_index": int(row.segment_index),
        "version": int(row.version),
        "start_ms": int(row.start_ms),
        "end_ms": int(row.end_ms),
        "text": str(row.text),
        "normalized_text": row.normalized_text,
        "language_code": row.language_code,
        "status": _enum_value(row.status),
        "confidence": row.confidence,
        "difficulty_flags_json": _json_safe(row.difficulty_flags_json),
        "analysis_version": row.analysis_version,
        "created_by_job_id": str(row.created_by_job_id) if row.created_by_job_id else None,
        "is_current": bool(row.is_current),
        "metadata_json": _json_safe(row.metadata_json),
    }


def _translation_authority(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source_video_id": str(row.source_video_id),
        "transcript_segment_id": str(row.transcript_segment_id),
        "segment_index": int(row.segment_index) if row.segment_index is not None else None,
        "version": int(row.version),
        "language_code": str(row.language_code),
        "text": str(row.text),
        "status": _enum_value(row.status),
        "translation_preset": row.translation_preset,
        "duration_budget_ms": row.duration_budget_ms,
        "estimated_tts_duration_ms": row.estimated_tts_duration_ms,
        "quality_flags_json": _json_safe(row.quality_flags_json),
        "created_by_job_id": str(row.created_by_job_id) if row.created_by_job_id else None,
        "is_current": bool(row.is_current),
        "metadata_json": _json_safe(row.metadata_json),
    }


def build_review_payload(
    rows: Sequence[Any],
    *,
    source_video_id: UUID,
    suggested_text_by_translation_id: Mapping[str, str] | None = None,
    authority_refs: Sequence[Mapping[str, Any]] = (),
    supersedes: Mapping[str, Any] | None = None,
    required_approval_token: str = "DIALOGUE_TRANSLATION_APPROVED",
    created_at: str | None = None,
) -> dict[str, Any]:
    if not rows:
        raise DialogueTranslationReviewError("No current translation segments found")
    suggestions = dict(suggested_text_by_translation_id or {})
    segments: list[dict[str, Any]] = []
    for row in rows:
        transcript = row.transcript_segment
        if transcript is None:
            raise DialogueTranslationReviewError("Translation is missing transcript authority")
        if str(row.source_video_id) != str(source_video_id):
            raise DialogueTranslationReviewError("Translation belongs to another source video")
        if not bool(row.is_current) or not bool(transcript.is_current):
            raise DialogueTranslationReviewError("Review requires current translation and transcript rows")
        slot_ms = int(row.duration_budget_ms or (transcript.end_ms - transcript.start_ms))
        if slot_ms <= 0 or int(transcript.end_ms) <= int(transcript.start_ms):
            raise DialogueTranslationReviewError("Review requires valid positive timing")

        translation = _translation_authority(row)
        transcript_payload = _transcript_authority(transcript)
        current_budget = assess_speech_budget(
            str(row.text), slot_seconds=slot_ms / 1000.0
        ).to_dict()
        estimated_ms = row.estimated_tts_duration_ms
        overrun_ms = max(0, int(estimated_ms or 0) - slot_ms)
        required_rate = (
            round(float(estimated_ms) / float(slot_ms), 6)
            if estimated_ms and slot_ms
            else None
        )
        suggestion = str(suggestions.get(str(row.id)) or "").strip() or None
        suggestion_budget = (
            assess_speech_budget(suggestion, slot_seconds=slot_ms / 1000.0).to_dict()
            if suggestion
            else None
        )
        authority = {"translation": translation, "transcript": transcript_payload}
        segments.append(
            {
                "translation_id": str(row.id),
                "segment_index": translation["segment_index"],
                "timing": {
                    "start_ms": int(transcript.start_ms),
                    "end_ms": int(transcript.end_ms),
                    "duration_budget_ms": slot_ms,
                    "estimated_tts_duration_ms": estimated_ms,
                    "estimated_overrun_ms": overrun_ms,
                    "required_rate_to_fit": required_rate,
                },
                "source_text": str(transcript.text),
                "current_candidate_text": str(row.text),
                "current_candidate_budget": current_budget,
                "suggested_review_text": suggestion,
                "suggested_review_budget": suggestion_budget,
                "translation_status": _enum_value(row.status),
                "translation_preset": row.translation_preset,
                "quality_flags": list((row.quality_flags_json or {}).get("flags", [])),
                "authority": authority,
                "translation_authority_sha256": _sha256_json(translation),
                "transcript_authority_sha256": _sha256_json(transcript_payload),
                "segment_authority_sha256": _sha256_json(authority),
            }
        )

    review_input = {
        "schema_version": SCHEMA_VERSION,
        "source_video_id": str(source_video_id),
        "segment_authority_sha256": [
            segment["segment_authority_sha256"] for segment in segments
        ],
        "authority_refs": _json_safe(list(authority_refs)),
        "supersedes": _json_safe(dict(supersedes or {})) or None,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PENDING_OPERATOR_REVIEW",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "source_video_id": str(source_video_id),
        "required_approval_token": str(required_approval_token).strip(),
        "operator_approval_written": False,
        "operator_decision": None,
        "review_input_sha256": _sha256_json(review_input),
        "authority_refs": review_input["authority_refs"],
        "supersedes": review_input["supersedes"],
        "segments": segments,
    }
    payload["artifact_sha256"] = _sha256_json(payload)
    return payload


def verify_review_payload(payload: Mapping[str, Any]) -> None:
    candidate = dict(payload)
    expected = str(candidate.pop("artifact_sha256", ""))
    if len(expected) != 64 or _sha256_json(candidate) != expected:
        raise DialogueTranslationReviewError("Dialogue translation review artifact hash mismatch")
    if candidate.get("operator_approval_written") is not False:
        raise DialogueTranslationReviewError("Review preparation must not write operator approval")


def verify_approval_payload(payload: Mapping[str, Any]) -> None:
    candidate = dict(payload)
    expected = str(candidate.pop("approval_sha256", ""))
    if len(expected) != 64 or _sha256_json(candidate) != expected:
        raise DialogueTranslationReviewError("Dialogue translation approval hash mismatch")
    if candidate.get("status") != "DIALOGUE_TRANSLATION_APPROVED":
        raise DialogueTranslationReviewError("Dialogue translation approval status is invalid")
    if candidate.get("operator_approval_written") is not True:
        raise DialogueTranslationReviewError("Dialogue translation approval is incomplete")


def _supersede_active_approval(
    root: Path,
    *,
    prior_review: Mapping[str, Any],
    prior_approval: Mapping[str, Any],
    next_review: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Archive an approved review before exposing a revised active candidate."""

    safe_reason = str(reason or "").strip()
    if not safe_reason:
        raise DialogueTranslationReviewError(
            "Superseding an approved dialogue review requires a reason"
        )
    verify_review_payload(prior_review)
    verify_approval_payload(prior_approval)
    verify_review_payload(next_review)
    prior_review_sha = str(prior_review.get("artifact_sha256") or "")
    prior_approval_sha = str(prior_approval.get("approval_sha256") or "")
    if str(dict(prior_approval.get("review_ref") or {}).get("artifact_sha256") or "") != prior_review_sha:
        raise DialogueTranslationReviewError(
            "Existing dialogue approval targets another review"
        )
    history_dir = root / "dialogue_translation_review_history"
    review_history_path = history_dir / f"review_{prior_review_sha}.json"
    approval_history_path = history_dir / f"approval_{prior_approval_sha}.json"
    for path, payload in (
        (review_history_path, prior_review),
        (approval_history_path, prior_approval),
    ):
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DialogueTranslationReviewError(
                    "Dialogue review history contains an invalid artifact"
                ) from exc
            if _sha256_json(existing) != _sha256_json(payload):
                raise DialogueTranslationReviewError(
                    "Dialogue review history artifact collision"
                )
        else:
            _write_json_atomic(path, payload)
    supersession: dict[str, Any] = {
        "schema_version": "dialogue_translation_review_supersession_v1",
        "status": "APPROVED_REVIEW_SUPERSEDED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": safe_reason,
        "prior_review_ref": {
            "path": review_history_path.relative_to(root).as_posix(),
            "artifact_sha256": prior_review_sha,
        },
        "prior_approval_ref": {
            "path": approval_history_path.relative_to(root).as_posix(),
            "approval_sha256": prior_approval_sha,
        },
        "next_review_artifact_sha256": next_review.get("artifact_sha256"),
    }
    supersession["supersession_sha256"] = _sha256_json(supersession)
    _write_json_atomic(
        history_dir / f"supersession_{supersession['supersession_sha256']}.json",
        supersession,
    )
    approval_path = root / "phase4_dialogue_translation_approval.json"
    if approval_path.is_file():
        approval_path.unlink()
    return supersession


def _load_current_rows(db: Session, source_video_id: UUID) -> list[TranslationSegment]:
    return list(
        db.scalars(
            select(TranslationSegment)
            .where(
                TranslationSegment.source_video_id == source_video_id,
                TranslationSegment.is_current.is_(True),
            )
            .options(selectinload(TranslationSegment.transcript_segment))
            .order_by(TranslationSegment.segment_index.asc())
        )
    )


def _assert_approval_matches_db(
    approval: Mapping[str, Any], rows: Sequence[Any]
) -> None:
    row_by_id = {str(row.id): row for row in rows}
    for segment in list(approval.get("segments") or []):
        if not isinstance(segment, Mapping):
            raise DialogueTranslationReviewError("Approval contains an invalid segment")
        row = row_by_id.get(str(segment.get("translation_id") or ""))
        if row is None:
            raise DialogueTranslationReviewError("Approved translation row is no longer current")
        if _sha256_json(_translation_authority(row)) != str(
            segment.get("approved_translation_authority_sha256") or ""
        ):
            raise DialogueTranslationReviewError("Approved translation DB authority changed")
        if _sha256_json(_transcript_authority(row.transcript_segment)) != str(
            segment.get("approved_transcript_authority_sha256") or ""
        ):
            raise DialogueTranslationReviewError("Approved transcript DB authority changed")


def approve_dialogue_translation_review(
    db: Session,
    *,
    source_video_id: UUID,
    root_dir: str | Path,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    """Materialize the exact reviewed suggestion; never starts or approves TTS."""

    root = Path(root_dir).resolve()
    review_path = root / "phase4_dialogue_translation_review.json"
    approval_path = root / "phase4_dialogue_translation_approval.json"
    operator = str(operator_id or "").strip()
    token = str(approval_token or "").strip()
    if not operator:
        raise DialogueTranslationReviewError("Dialogue translation approval requires an operator id")
    if not review_path.is_file():
        raise DialogueTranslationReviewError("Dialogue translation review artifact is missing")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if not isinstance(review, Mapping):
        raise DialogueTranslationReviewError("Dialogue translation review artifact is invalid")
    verify_review_payload(review)
    if str(review.get("source_video_id") or "") != str(source_video_id):
        raise DialogueTranslationReviewError("Dialogue review belongs to another source video")
    if token != str(review.get("required_approval_token") or ""):
        raise DialogueTranslationReviewError("Dialogue translation approval token mismatch")

    rows = _load_current_rows(db, source_video_id)
    if approval_path.is_file():
        existing = json.loads(approval_path.read_text(encoding="utf-8"))
        if not isinstance(existing, Mapping):
            raise DialogueTranslationReviewError("Existing dialogue approval is invalid")
        verify_approval_payload(existing)
        if str(existing.get("review_ref", {}).get("artifact_sha256") or "") != str(
            review.get("artifact_sha256") or ""
        ):
            raise DialogueTranslationReviewError("Existing approval targets another review")
        _assert_approval_matches_db(existing, rows)
        return dict(existing)

    row_by_id = {str(row.id): row for row in rows}
    review_segments = list(review.get("segments") or [])
    if not review_segments or len(review_segments) != len(rows):
        raise DialogueTranslationReviewError("Current DB translation set differs from review")

    edits: list[SegmentEdit] = []
    approved_at = datetime.now(timezone.utc).isoformat()
    pre_authority_matches = True
    for raw_segment in review_segments:
        if not isinstance(raw_segment, Mapping):
            raise DialogueTranslationReviewError("Review contains an invalid segment")
        row = row_by_id.get(str(raw_segment.get("translation_id") or ""))
        if row is None:
            raise DialogueTranslationReviewError("Reviewed translation row is no longer current")
        current_hash = _sha256_json(
            {
                "translation": _translation_authority(row),
                "transcript": _transcript_authority(row.transcript_segment),
            }
        )
        if current_hash != str(raw_segment.get("segment_authority_sha256") or ""):
            pre_authority_matches = False
        approved_text = str(
            raw_segment.get("suggested_review_text")
            or raw_segment.get("current_candidate_text")
            or ""
        ).strip()
        if not approved_text:
            raise DialogueTranslationReviewError("Approved dialogue text is empty")
        edits.append(
            SegmentEdit(
                transcript_segment_id=row.transcript_segment.id,
                translation_segment_id=row.id,
                start_ms=int(row.transcript_segment.start_ms),
                end_ms=int(row.transcript_segment.end_ms),
                source_text=str(row.transcript_segment.text),
                translated_text=approved_text,
                status=TranscriptSegmentStatus.APPROVED,
            )
        )

    already_materialized = all(
        row.status == TranscriptSegmentStatus.APPROVED
        and row.text.strip() == edit.translated_text
        for row, edit in zip(rows, edits)
    )
    if not pre_authority_matches and not already_materialized:
        raise DialogueTranslationReviewError(
            "Dialogue translation or transcript changed after review; approval is stale"
        )

    if not already_materialized:
        TranscriptEditService(db).save_draft(
            source_video_id,
            edits,
            commit=False,
        )
    for row, raw_segment, edit in zip(rows, review_segments, edits):
        budget = raw_segment.get("suggested_review_budget") or raw_segment.get(
            "current_candidate_budget"
        )
        if isinstance(budget, Mapping):
            estimated_seconds = budget.get("estimated_duration_seconds")
            if estimated_seconds is not None:
                row.estimated_tts_duration_ms = int(
                    round(float(estimated_seconds) * 1000.0)
                )
        row.status = TranscriptSegmentStatus.APPROVED
        row.metadata_json = {
            **(row.metadata_json or {}),
            "dialogue_translation_review": {
                "status": "DIALOGUE_TRANSLATION_APPROVED",
                "approved_at": approved_at,
                "operator_id": operator,
                "review_input_sha256": review.get("review_input_sha256"),
                "review_artifact_sha256": review.get("artifact_sha256"),
                "approved_text_sha256": hashlib.sha256(
                    edit.translated_text.encode("utf-8")
                ).hexdigest(),
            },
        }
    db.flush()

    approval_segments: list[dict[str, Any]] = []
    for row, raw_segment, edit in zip(rows, review_segments, edits):
        approval_segments.append(
            {
                "translation_id": str(row.id),
                "transcript_segment_id": str(row.transcript_segment_id),
                "segment_index": row.segment_index,
                "approved_text": edit.translated_text,
                "approved_text_sha256": hashlib.sha256(
                    edit.translated_text.encode("utf-8")
                ).hexdigest(),
                "start_ms": int(row.transcript_segment.start_ms),
                "end_ms": int(row.transcript_segment.end_ms),
                "pre_approval_segment_authority_sha256": raw_segment.get(
                    "segment_authority_sha256"
                ),
                "approved_translation_authority_sha256": _sha256_json(
                    _translation_authority(row)
                ),
                "approved_transcript_authority_sha256": _sha256_json(
                    _transcript_authority(row.transcript_segment)
                ),
            }
        )
    approval: dict[str, Any] = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "status": "DIALOGUE_TRANSLATION_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
        "operator_approval_written": True,
        "source_video_id": str(source_video_id),
        "review_ref": {
            "path": review_path.relative_to(root).as_posix(),
            "file_sha256": _sha256_file(review_path),
            "artifact_sha256": review.get("artifact_sha256"),
            "review_input_sha256": review.get("review_input_sha256"),
        },
        "segments": approval_segments,
        "tts_synthesis_triggered": False,
        "audio_approval_written": False,
    }
    approval["approval_sha256"] = _sha256_json(approval)
    db.commit()
    _write_json_atomic(approval_path, approval)
    return approval


def prepare_dialogue_translation_review(
    db: Session,
    *,
    source_video_id: UUID,
    root_dir: str | Path,
    suggested_text_by_translation_id: Mapping[str, str] | None = None,
    authority_paths: Sequence[str | Path] = (),
    required_approval_token: str = "DIALOGUE_TRANSLATION_APPROVED",
    supersede_approved: bool = False,
    supersede_reason: str | None = None,
) -> dict[str, Any]:
    rows = _load_current_rows(db, source_video_id)
    root = Path(root_dir).resolve()
    authority_refs: list[dict[str, Any]] = []
    for raw_path in authority_paths:
        path = Path(raw_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise DialogueTranslationReviewError(
                "Associated authority must be an existing file inside the regression root"
            )
        authority_refs.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
            }
        )
    prior_review: dict[str, Any] | None = None
    prior_approval: dict[str, Any] | None = None
    approval_path = root / "phase4_dialogue_translation_approval.json"
    review_path = root / "phase4_dialogue_translation_review.json"
    supersedes: dict[str, Any] | None = None
    if approval_path.is_file():
        if not supersede_approved:
            raise DialogueTranslationReviewError(
                "An approved dialogue review already exists; explicit supersession is required"
            )
        try:
            prior_review = json.loads(review_path.read_text(encoding="utf-8"))
            prior_approval = json.loads(approval_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DialogueTranslationReviewError(
                "Existing dialogue review authority is invalid"
            ) from exc
        if not isinstance(prior_review, Mapping) or not isinstance(prior_approval, Mapping):
            raise DialogueTranslationReviewError(
                "Existing dialogue review authority is invalid"
            )
        verify_review_payload(prior_review)
        verify_approval_payload(prior_approval)
        _assert_approval_matches_db(prior_approval, rows)
        supersedes = {
            "reason": str(supersede_reason or "").strip(),
            "review_artifact_sha256": prior_review.get("artifact_sha256"),
            "approval_sha256": prior_approval.get("approval_sha256"),
        }
    payload = build_review_payload(
        rows,
        source_video_id=source_video_id,
        suggested_text_by_translation_id=suggested_text_by_translation_id,
        authority_refs=authority_refs,
        supersedes=supersedes,
        required_approval_token=required_approval_token,
    )
    verify_review_payload(payload)
    if prior_review is not None and prior_approval is not None:
        _supersede_active_approval(
            root,
            prior_review=prior_review,
            prior_approval=prior_approval,
            next_review=payload,
            reason=str(supersede_reason or ""),
        )
    _write_json_atomic(review_path, payload)
    return payload
