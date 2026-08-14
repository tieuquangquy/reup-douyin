"""Hash-bound handoff contract from Translation Draft to TTS."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


TRANSLATION_AUTHORITY_SCHEMA_VERSION = "translation-authority-v1"


def sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def transcript_authority_payload(rows: Sequence[object]) -> list[dict[str, Any]]:
    return [
        {
            "segment_index": int(row.segment_index),
            "start_ms": int(row.start_ms),
            "end_ms": int(row.end_ms),
            "text": str(row.text or ""),
            "normalized_text": str(row.normalized_text or ""),
            "confidence": row.confidence,
            "speaker_label": getattr(row, "speaker_label", None),
            "flags": list((row.difficulty_flags_json or {}).get("flags") or []),
        }
        for row in rows
    ]


def transcript_authority_sha256(rows: Sequence[object]) -> str:
    return sha256_json(transcript_authority_payload(rows))


def translation_rows_payload(rows: Sequence[object]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in sorted(
        rows,
        key=lambda value: (
            int(getattr(value, "segment_index", 0) or 0),
            str(getattr(value, "id", "")),
        ),
    ):
        raw_status = getattr(row, "status", None)
        output.append(
            {
                "translation_segment_id": str(getattr(row, "id", "")),
                "transcript_segment_id": str(getattr(row, "transcript_segment_id", "")),
                "segment_index": int(getattr(row, "segment_index", 0) or 0),
                "version": int(getattr(row, "version", 1) or 1),
                "text": str(getattr(row, "text", "") or ""),
                "status": str(getattr(raw_status, "value", raw_status) or ""),
                "translation_preset": str(getattr(row, "translation_preset", "") or ""),
                "duration_budget_ms": int(getattr(row, "duration_budget_ms", 0) or 0),
                "estimated_tts_duration_ms": (
                    int(getattr(row, "estimated_tts_duration_ms"))
                    if getattr(row, "estimated_tts_duration_ms", None) is not None
                    else None
                ),
                "quality_flags": list(
                    (getattr(row, "quality_flags_json", None) or {}).get("flags") or []
                ),
            }
        )
    return output


def translation_rows_sha256(rows: Sequence[object]) -> str:
    return sha256_json(translation_rows_payload(rows))


def build_translation_authority(
    *,
    source_video_id: object,
    analysis_version: str,
    source_transcript_sha256: str,
    translation_fingerprint: str,
    prompt: str | None,
    provider_identity: Mapping[str, object],
    quality_contract: Mapping[str, object],
    translation_rows: Sequence[object],
    job_id: object | None,
) -> dict[str, Any]:
    return {
        "schema_version": TRANSLATION_AUTHORITY_SCHEMA_VERSION,
        "source_video_id": str(source_video_id),
        "analysis_version": str(analysis_version),
        "source_transcript_sha256": str(source_transcript_sha256),
        "translation_fingerprint": str(translation_fingerprint),
        "prompt_sha256": hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest(),
        "provider_identity": dict(provider_identity),
        "quality_contract_sha256": sha256_json(dict(quality_contract)),
        "translation_rows_sha256": translation_rows_sha256(translation_rows),
        "translation_row_count": len(translation_rows),
        "tts_ready": bool(quality_contract.get("tts_ready")),
        "operator_approved": False,
        "operator_approval_binding_sha256": None,
        "job_id": str(job_id) if job_id else None,
    }


def validate_translation_authority(
    manifest: Mapping[str, object],
    *,
    source_video_id: object,
    transcript_rows: Sequence[object],
    translation_rows: Sequence[object],
) -> tuple[bool, str | None]:
    if manifest.get("schema_version") != TRANSLATION_AUTHORITY_SCHEMA_VERSION:
        return False, "unsupported_translation_authority_schema"
    if str(manifest.get("source_video_id") or "") != str(source_video_id):
        return False, "translation_authority_source_video_mismatch"
    if int(manifest.get("translation_row_count") or 0) != len(translation_rows):
        return False, "translation_authority_row_count_mismatch"
    if str(manifest.get("source_transcript_sha256") or "") != transcript_authority_sha256(
        transcript_rows
    ):
        return False, "translation_authority_transcript_hash_mismatch"
    if str(manifest.get("translation_rows_sha256") or "") != translation_rows_sha256(
        translation_rows
    ):
        return False, "translation_authority_rows_hash_mismatch"
    return True, None
