"""Audit stored dialogue verdicts against measured Silero VAD speech.

Answers "did the pipeline mislabel any video?". Read-only unless ``--reanalyze`` is
passed, which enqueues ANALYZE_AUDIO for the flagged videos so the measured VAD gate
can correct them.

    python scripts/audit_dialogue_detection.py [--limit 20] [--reanalyze]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from src.audio_pipeline.silero_vad_runner import run_silero_speech_summary, silero_is_importable
from src.core.settings import get_settings
from src.db.session import get_session_factory

MIN_SPEECH_SECONDS = 0.8


def _audio_path_for(storage_root: Path, relative_path: str) -> Path:
    return (storage_root / relative_path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--reanalyze",
        action="store_true",
        help="Enqueue ANALYZE_AUDIO for flagged videos so measured VAD can correct them.",
    )
    args = parser.parse_args()

    if not silero_is_importable():
        print("silero-vad is not installed: pip install silero-vad")
        return 2

    storage_root = Path(get_settings().local_storage_root)
    rows = []
    with get_session_factory()() as db:
        rows = db.execute(
            text(
                """
                SELECT sv.id::text AS sv_id,
                       sv.source_video_external_id AS aweme,
                       sv.metadata_json->>'dialogue_phase' AS phase,
                       sv.metadata_json->>'has_speech' AS has_speech,
                       sv.metadata_json->>'transcript_count' AS transcript_count,
                       ma.relative_path AS relative_path
                FROM source_videos sv
                JOIN media_assets ma
                  ON ma.source_video_id = sv.id
                 AND ma.asset_type = 'SOURCE_VIDEO_RAW'
                 AND ma.is_current
                WHERE sv.metadata_json->>'dialogue_phase' IS NOT NULL
                ORDER BY sv.updated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": args.limit},
        ).fetchall()

    suspicious = 0
    flagged: list[str] = []
    print(f"{'aweme':<22}{'stored':<20}{'beats':<7}{'speech_s':<10}{'ratio':<8}verdict")
    for row in rows:
        record = dict(row._mapping)
        path = _audio_path_for(storage_root, record["relative_path"])
        if not path.exists():
            print(f"{record['aweme']:<22}{record['phase']:<20}{'-':<7}{'-':<10}{'-':<8}media missing")
            continue
        try:
            summary = run_silero_speech_summary(str(path))
        except Exception as exc:  # noqa: BLE001
            print(f"{record['aweme']:<22}{record['phase']:<20}{'-':<7}{'-':<10}{'-':<8}vad failed: {exc}")
            continue

        beats = int(record["transcript_count"] or 0)
        measured_speech = summary.speech_seconds >= MIN_SPEECH_SECONDS
        ratio = summary.speech_seconds / summary.audio_seconds if summary.audio_seconds else 0.0
        if beats == 0 and measured_speech:
            verdict = "SUSPECT: speech measured but no transcript"
            suspicious += 1
            flagged.append(record["sv_id"])
        elif beats > 0 and not measured_speech:
            verdict = "SUSPECT: transcript without measured speech"
            suspicious += 1
            flagged.append(record["sv_id"])
        else:
            verdict = "consistent"
        print(
            f"{record['aweme']:<22}{record['phase']:<20}{beats:<7}"
            f"{summary.speech_seconds:<10.1f}{ratio:<8.3f}{verdict}"
        )

    print(f"\n{len(rows)} videos audited, {suspicious} suspicious.")
    if args.reanalyze and flagged:
        print(f"Enqueuing ANALYZE_AUDIO for {len(flagged)} flagged videos...")
        for job_id, sv_id in _enqueue_reanalysis(flagged):
            print(f"  {sv_id[:8]} -> job {job_id[:8]}")
    return 0


def _enqueue_reanalysis(source_video_ids: list[str]) -> list[tuple[str, str]]:
    """Re-run analyze so the measured VAD gate replaces the unverified verdict."""
    from datetime import UTC, datetime
    from uuid import UUID

    from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
    from src.audio_pipeline.types import AudioAnalysisRequest

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    created: list[tuple[str, str]] = []
    with get_session_factory()() as db:
        service = AudioAnalysisService(db)
        for sv_id in source_video_ids:
            job = service.create_analysis_job(
                AudioAnalysisRequest(
                    source_video_id=UUID(sv_id),
                    force_refresh=True,
                    skip_translation=True,
                ),
                idempotency_key=f"vad-audit:{sv_id}:{stamp}",
            )
            created.append((str(job.id), sv_id))
        db.commit()
    return created


if __name__ == "__main__":
    sys.exit(main())
