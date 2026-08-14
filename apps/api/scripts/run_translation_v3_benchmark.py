"""Run durable Translation V3 jobs and print a machine-readable benchmark summary."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from src.audio_pipeline.machine_translate import contains_cjk
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.translation_v3 import TRANSLATION_V3_RECIPE_VERSION
from src.db.session import get_session_factory
from src.enums import JobStatus, TranscriptSegmentStatus
from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.ingestion import SourceVideo
from src.models.jobs import Job


DEFAULT_SOURCE_IDS = (
    "5dc0dfd7-63fc-4b1b-a00a-e36474661cca",
    "89a84aed-ec32-4bf5-866c-f134990e1e9e",
    "3b6599c2-9beb-4fe3-8370-4c6329da429d",
    "be200f16-7eea-46b5-b258-c4a609dadede",
    "facf2c24-f88e-429e-b1f1-594e6da93a8e",
)
TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.WAITING_FOR_REVIEW,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_ids", nargs="*", default=list(DEFAULT_SOURCE_IDS))
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    source_ids = [UUID(value) for value in args.source_ids]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.perf_counter()
    results = [
        run_one(
            source_id,
            run_id=run_id,
            timeout_seconds=max(1.0, args.timeout_seconds),
            poll_seconds=max(0.1, args.poll_seconds),
        )
        for source_id in source_ids
    ]
    payload = {
        "run_id": run_id,
        "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "results": results,
        "totals": summarize(results),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if all(row["status"] == JobStatus.COMPLETED for row in results) else 1


def run_one(
    source_id: UUID,
    *,
    run_id: str,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict:
    factory = get_session_factory()
    with factory() as db:
        source = db.get(SourceVideo, source_id)
        if source is None:
            return {"source_video_id": str(source_id), "status": "SOURCE_NOT_FOUND"}
        current = list(
            db.scalars(
                select(TranscriptSegment).where(
                    TranscriptSegment.source_video_id == source_id,
                    TranscriptSegment.is_current.is_(True),
                )
            )
        )
        if current and any(row.status != TranscriptSegmentStatus.APPROVED for row in current):
            return {
                "source_video_id": str(source_id),
                "douyin_id": source.source_video_external_id,
                "status": "SOURCE_NOT_APPROVED",
            }
        job = AudioAnalysisService(db).create_translation_job(
            source_id,
            force_refresh=True,
            idempotency_key=f"translation-v3-premerge-benchmark:{run_id}:{source_id}",
        )
        job_id = job.id
        db.commit()

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with factory() as db:
            job = db.get(Job, job_id)
            if job is None:
                return {"source_video_id": str(source_id), "job_id": str(job_id), "status": "JOB_NOT_FOUND"}
            if job.status in TERMINAL_STATUSES:
                return collect_result(db, source_id=source_id, job=job)
        time.sleep(poll_seconds)
    return {"source_video_id": str(source_id), "job_id": str(job_id), "status": "TIMEOUT"}


def collect_result(db, *, source_id: UUID, job: Job) -> dict:
    source = db.get(SourceVideo, source_id)
    transcripts = list(
        db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.source_video_id == source_id,
                TranscriptSegment.is_current.is_(True),
            )
            .order_by(TranscriptSegment.start_ms.asc())
        )
    )
    translations = list(
        db.scalars(
            select(TranslationSegment)
            .where(
                TranslationSegment.source_video_id == source_id,
                TranslationSegment.is_current.is_(True),
            )
            .order_by(TranslationSegment.segment_index.asc())
        )
    )
    contract = dict((source.metadata_json or {}).get("translation_quality_contract") or {})
    premerge = dict((source.metadata_json or {}).get("translation_temporal_premerge") or {})
    ratios = [
        float(row.estimated_tts_duration_ms) / float(row.duration_budget_ms)
        for row in translations
        if row.estimated_tts_duration_ms is not None and row.duration_budget_ms
    ]
    v3_payloads = [dict((row.metadata_json or {}).get("translation_v3") or {}) for row in translations]
    flags = [
        flag
        for row in translations
        for flag in list((row.quality_flags_json or {}).get("flags") or [])
    ]
    active_seconds = None
    if job.started_at is not None and job.finished_at is not None:
        active_seconds = round((job.finished_at - job.started_at).total_seconds(), 3)
    return {
        "source_video_id": str(source_id),
        "douyin_id": source.source_video_external_id,
        "job_id": str(job.id),
        "status": job.status,
        "attempts": int(job.attempts or 0),
        "active_seconds": active_seconds,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "transcript_count": len(transcripts),
        "translation_count": len(translations),
        "block_count": len({row.get("block_id") for row in v3_payloads if row.get("block_id")}),
        "candidate_count": sum(int(row.get("candidate_count") or 0) for row in v3_payloads),
        "row_fallback_count": sum(row.get("status") == "row_fallback" for row in v3_payloads),
        "provider_fallback_count": flags.count("translation_fallback_used"),
        "final_cjk_count": sum(contains_cjk(row.text or "") for row in translations),
        "within_8_percent": sum(abs(ratio - 1.0) <= 0.08 for ratio in ratios),
        "within_12_percent": sum(abs(ratio - 1.0) <= 0.12 for ratio in ratios),
        "within_15_percent": sum(abs(ratio - 1.0) <= 0.15 for ratio in ratios),
        "measured_ratio_count": len(ratios),
        "quality_contract": contract,
        "translation_premerge": premerge,
    }


def summarize(results: list[dict]) -> dict:
    completed = [row for row in results if row.get("status") == JobStatus.COMPLETED]
    ratio_total = sum(int(row.get("measured_ratio_count") or 0) for row in completed)
    within_12 = sum(int(row.get("within_12_percent") or 0) for row in completed)
    return {
        "requested": len(results),
        "completed": len(completed),
        "first_attempt_completed": sum(int(row.get("attempts") or 0) == 1 for row in completed),
        "transcript_count": sum(int(row.get("transcript_count") or 0) for row in completed),
        "translation_count": sum(int(row.get("translation_count") or 0) for row in completed),
        "candidate_count": sum(int(row.get("candidate_count") or 0) for row in completed),
        "row_fallback_count": sum(int(row.get("row_fallback_count") or 0) for row in completed),
        "provider_fallback_count": sum(int(row.get("provider_fallback_count") or 0) for row in completed),
        "final_cjk_count": sum(int(row.get("final_cjk_count") or 0) for row in completed),
        "blocked_count": sum(
            int((row.get("quality_contract") or {}).get("blocked_count") or 0)
            for row in completed
        ),
        "complete_contracts": sum(
            bool((row.get("quality_contract") or {}).get("complete")) for row in completed
        ),
        "tts_ready_contracts": sum(
            bool((row.get("quality_contract") or {}).get("tts_ready")) for row in completed
        ),
        "within_12_percent": within_12,
        "measured_ratio_count": ratio_total,
        "within_12_percent_rate": round(within_12 / ratio_total, 4) if ratio_total else None,
        "active_seconds": round(sum(float(row.get("active_seconds") or 0.0) for row in completed), 3),
    }


if __name__ == "__main__":
    raise SystemExit(main())
