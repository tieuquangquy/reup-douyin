from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(ROOT))
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    import os

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_engine, get_session_factory
from src.enums import CandidateStatus
from src.models.review import VideoCandidate
from src.schemas.candidates import CandidateDetailResponse

PROTECTED_FIELDS = (
    "reup_score",
    "estimated_views_display",
    "estimated_views_min",
    "estimated_views_max",
    "estimated_views_mid",
    "duration_text",
    "duration_seconds",
    "posted_display",
    "posted_at",
    "thumbnail_url",
    "like_count",
    "comment_count",
    "share_count",
    "caption",
    "title",
    "source_url",
    "video_url",
    "profile_url",
    "aweme_id",
    "capture_item_id",
    "source_capture_item_id",
    "review_status",
    "decision_status",
    "notes",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Review Board metadata contract without modifying data.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum active candidates to scan.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON summary.")
    args = parser.parse_args()

    engine = get_engine()
    session_factory = get_session_factory()
    violations: list[dict[str, Any]] = []
    checked = 0
    with session_factory() as db:
        candidates = list(
            db.scalars(
                select(VideoCandidate)
                .options(selectinload(VideoCandidate.source_video))
                .where(VideoCandidate.status != CandidateStatus.ARCHIVED)
                .limit(args.limit)
            ).unique()
        )
        for candidate in candidates:
            checked += 1
            response = CandidateDetailResponse.model_validate(candidate)
            debug = response.review_candidate_debug or {}
            metadata = response.metadata_json or {}
            source_metadata = response.source_metadata or {}
            candidate_label = str(candidate.id)
            if response.reup_score is None and response.score is not None and debug.get("scoreSource") != "missing":
                violations.append(issue(candidate_label, "score", "missing reup_score must not fall back to internal candidate.score", debug.get("scoreSource")))
            if response.reup_score is not None and debug.get("scoreValue") != response.reup_score:
                violations.append(issue(candidate_label, "reup_score", "debug scoreValue must equal canonical reup_score", debug.get("scoreValue")))
            if response.estimated_views_display is None:
                for field in ("estimated_views_min", "estimated_views_max", "estimated_views_mid"):
                    if getattr(response, field) == 0 and source_metadata.get(field) is None and metadata.get(field) is None:
                        violations.append(issue(candidate_label, field, "missing estimated views must not be synthesized as 0", getattr(response, field)))
            for field in ("like_count", "comment_count", "share_count"):
                if getattr(response, field) == 0 and source_metadata.get(field) is None and metadata.get(field) is None:
                    violations.append(issue(candidate_label, field, "missing metric must not be synthesized as 0", getattr(response, field)))
            if response.posted_display and debug.get("postedDisplayWasFormatted"):
                violations.append(issue(candidate_label, "posted_display", "Review Board posted display should come from captured display text, not date-only reformatting", response.posted_display))
            if metadata.get("decision_status") and response.decision_status != metadata.get("decision_status"):
                violations.append(issue(candidate_label, "decision_status", "candidate decision_status must be preserved", response.decision_status))

    summary = {
        "phase": "22F-1G",
        "database": {"driver": engine.url.drivername, "host": engine.url.host, "database": engine.url.database},
        "checked": checked,
        "protected_fields": PROTECTED_FIELDS,
        "violations": violations,
        "ok": not violations,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"phase=22F-1G checked={checked} violations={len(violations)} db={engine.url.drivername}://{engine.url.host or ''}/{engine.url.database}")
        for violation in violations:
            print(f"VIOLATION candidate={violation['candidate_id']} field={violation['field']} value={violation['value']!r} message={violation['message']}")
        if not violations:
            print("Review Board metadata contract smoke check passed.")
    return 1 if violations else 0


def issue(candidate_id: str, field: str, message: str, value: Any) -> dict[str, Any]:
    return {"candidate_id": candidate_id, "field": field, "message": message, "value": value}


if __name__ == "__main__":
    raise SystemExit(main())
