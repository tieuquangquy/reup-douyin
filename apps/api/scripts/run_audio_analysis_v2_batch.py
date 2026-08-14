"""Run a local Analyze Audio V2 benchmark against five existing source videos.

This intentionally does not download or translate anything.  It creates normal
durable ANALYZE_AUDIO jobs, executes them through JobRunner, and prints a JSON
report suitable for operator review.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.types import AudioAnalysisRequest
from src.db.session import get_session_factory
from src.enums import JobStatus, MediaAssetStatus, MediaAssetType
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.services.job_runner import JobRunner


def choose_sources(db) -> list[SourceVideo]:
    rows = list(
        db.scalars(
            select(SourceVideo)
            .join(MediaAsset, MediaAsset.source_video_id == SourceVideo.id)
            .where(
                MediaAsset.asset_type == MediaAssetType.SOURCE_VIDEO_RAW,
                MediaAsset.status == MediaAssetStatus.AVAILABLE,
                MediaAsset.is_current.is_(True),
                SourceVideo.duration_seconds > 5,
                SourceVideo.duration_seconds < 60,
            )
            .order_by(SourceVideo.updated_at.desc())
        ).unique()
    )
    requested = (os.getenv("AUDIO_V2_SOURCE_ID") or "").strip()
    if requested:
        rows = [source for source in rows if str(source.id) == requested]
    selected: list[SourceVideo] = []
    buckets: set[str] = set()
    for source in rows:
        duration = float(source.duration_seconds or 0.0)
        bucket = "short" if duration < 20 else "medium" if duration < 35 else "long"
        profile_id = str(getattr(source, "source_profile_id", ""))
        key = f"{bucket}:{profile_id}"
        if key in buckets:
            continue
        selected.append(source)
        buckets.add(key)
        if len(selected) >= (1 if requested else 5):
            break
    # If one profile does not have all duration buckets, fill deterministically.
    for source in rows:
        if len(selected) >= (1 if requested else 5):
            break
        if source.id not in {item.id for item in selected}:
            selected.append(source)
    return selected[: (1 if requested else 5)]


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = uuid4().hex[:12]
    db = get_session_factory()()
    try:
        sources = choose_sources(db)
        expected = 1 if os.getenv("AUDIO_V2_SOURCE_ID") else 5
        if len(sources) < expected:
            print(json.dumps({"status": "BLOCKED", "reason": "fewer_than_five_local_videos", "count": len(sources)}))
            return 2
        service = AudioAnalysisService(db)
        force_refresh = (os.getenv("AUDIO_V2_FORCE_REFRESH", "1").strip().lower() not in {"0", "false", "no"})
        jobs = []
        for source in sources:
            job = service.create_analysis_job(
                AudioAnalysisRequest(
                    source_video_id=source.id,
                    force_refresh=force_refresh,
                    skip_translation=True,
                ),
                idempotency_key=f"audio-v2-benchmark:{run_id}:{source.id}",
            )
            jobs.append(job)

        runner = JobRunner(db)
        reports: list[dict] = []
        for source, job in zip(sources, jobs, strict=True):
            started = time.perf_counter()
            try:
                result = runner.run_job(job.id)
                status = result.status.value if hasattr(result.status, "value") else str(result.status)
                persisted = dict(result.result_json or {})
                reports.append(
                    {
                        "source_video_id": str(source.id),
                        "external_id": str(source.source_video_external_id),
                        "duration_seconds": float(source.duration_seconds or 0.0),
                        "job_id": str(job.id),
                        "status": status,
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "result": persisted,
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                    }
                )
            except Exception as exc:  # keep the five-video report complete
                db.rollback()
                reports.append(
                    {
                        "source_video_id": str(source.id),
                        "external_id": str(source.source_video_external_id),
                        "duration_seconds": float(source.duration_seconds or 0.0),
                        "job_id": str(job.id),
                        "status": "HARNESS_ERROR",
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "error_code": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
        completed = sum(item["status"] == JobStatus.COMPLETED.value for item in reports)
        print(
            json.dumps(
                {
                    "status": "PASS" if completed == len(reports) == expected else "FAIL",
                    "run_id": run_id,
                    "started_at": started_at,
                    "completed": completed,
                    "total": len(reports),
                    "videos": reports,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if completed == expected else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
