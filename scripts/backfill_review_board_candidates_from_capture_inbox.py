from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(ROOT))
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        import os

        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_engine, get_session_factory
from src.enums import CandidateStatus
from src.models.review import VideoCandidate
from src.services.candidate_service import CandidateEvaluationService


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Review Board candidate metadata from Capture Inbox items.")
    parser.add_argument("--apply", action="store_true", help="Persist patches. Default is dry-run only.")
    args = parser.parse_args()

    engine = get_engine()
    session_factory = get_session_factory()
    visible_candidate_ids = {
        "91555cfa-37ea-4b6a-9be7-09a2cf7ba2ae",
        "7ff9c805-d5ea-4a8d-81ab-0d476d3a659e",
        "5f719234-f0c7-4199-a104-6568da05c75d",
    }
    visible_caption_prefixes = ("199", "202", "285")
    with session_factory() as db:
        service = CandidateEvaluationService(db)
        candidates = list(
            db.scalars(
                select(VideoCandidate)
                .options(selectinload(VideoCandidate.source_video))
                .where(VideoCandidate.status != CandidateStatus.ARCHIVED)
            ).unique()
        )
        missing_source_metadata = 0
        matched = 0
        updated = 0
        skipped = 0
        not_hydratable = 0
        skip_reasons: Counter[str] = Counter()
        print(
            "db="
            f"driver={engine.url.drivername} host={engine.url.host} database={engine.url.database} "
            f"apply={args.apply} phase=22F-1G scanned={len(candidates)}"
        )
        for candidate in candidates:
            before_metadata = dict(candidate.metadata_json or {})
            before_snapshot = before_metadata.get("source_metadata") if isinstance(before_metadata.get("source_metadata"), dict) else {}
            if not before_snapshot:
                missing_source_metadata += 1
            result = service.hydrateReviewCandidateFromCaptureItem(candidate, persist=args.apply)
            debug = result.get("debug", {})
            candidate_metadata = dict(candidate.metadata_json or before_metadata)
            if debug.get("matched"):
                matched += 1
                snapshot = candidate_metadata.get("source_metadata") if isinstance(candidate_metadata.get("source_metadata"), dict) else {}
                if snapshot:
                    snapshot = dict(snapshot)
                    snapshot["source_metadata_version"] = "22F-1G"
                    snapshot["snapshot_source"] = "live_db_backfill_22F_1G"
                    candidate_metadata["source_metadata"] = snapshot
                    comparison = candidate_metadata.get("capture_to_review_comparison")
                    if isinstance(comparison, dict):
                        comparison = dict(comparison)
                        comparison["traceVersion"] = "22F-1G"
                        candidate_metadata["capture_to_review_comparison"] = comparison
                    candidate_metadata["review_board_upsert_source"] = "live_db_backfill_22F_1G"
                    if args.apply:
                        candidate.metadata_json = candidate_metadata
                        if candidate.source_video is not None:
                            source_metadata = dict(candidate.source_video.metadata_json or {})
                            source_metadata["source_metadata"] = snapshot
                            if isinstance(candidate_metadata.get("capture_to_review_comparison"), dict):
                                source_metadata["capture_to_review_comparison"] = candidate_metadata["capture_to_review_comparison"]
                            source_metadata["review_board_upsert_source"] = "live_db_backfill_22F_1G"
                            candidate.source_video.metadata_json = source_metadata
                    updated += 1
                else:
                    skipped += 1
                    skip_reasons["matched_without_snapshot"] += 1
            else:
                skipped += 1
                not_hydratable += 1
                skip_reasons[debug.get("reason_if_not_matched") or "not_matched"] += 1
            caption = str(candidate_metadata.get("caption") or (candidate.source_video.caption if candidate.source_video else ""))
            is_visible = str(candidate.id) in visible_candidate_ids or caption.startswith(visible_caption_prefixes)
            if is_visible or debug.get("matched") is False:
                snapshot = candidate_metadata.get("source_metadata") if isinstance(candidate_metadata.get("source_metadata"), dict) else {}
                print(
                    f"candidate={candidate.id} visible_target={is_visible} status={candidate.status.value} "
                    f"matched={debug.get('matched')} match_key={debug.get('match_key')} capture_item_id={debug.get('capture_item_id')} "
                    f"updated={bool(debug.get('matched') and snapshot)} version={snapshot.get('source_metadata_version')} "
                    f"snapshot_source={snapshot.get('snapshot_source')} reup_score={snapshot.get('reup_score')} "
                    f"estimated_views={snapshot.get('estimated_views_display')} reason={debug.get('reason_if_not_matched')}"
                )
        summary = service.hydration_summary(candidates)
        print(
            "phase22f_1g_summary="
            f"scanned={len(candidates)} missing_source_metadata={missing_source_metadata} matched={matched} "
            f"updated={updated} skipped={skipped} not_hydratable={not_hydratable} skip_reasons={dict(skip_reasons)}"
        )
        print(f"api_hydration_summary={summary}")
        if args.apply:
            db.commit()
            print(f"applied updated={updated} not_hydratable={not_hydratable}")
        else:
            db.rollback()
            print(f"dry_run updated={updated} not_hydratable={not_hydratable}; rerun with --apply to persist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
