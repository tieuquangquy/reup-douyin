"""Prepare (but never approve) the operator dialogue review before TTS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from src.audio_pipeline.services.dialogue_translation_review import (
    prepare_dialogue_translation_review,
)
from src.db.session import get_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.prepare_dialogue_translation_review"
    )
    parser.add_argument("source_video_id")
    parser.add_argument("root_dir")
    parser.add_argument("--translation-id")
    parser.add_argument("--suggested-text")
    parser.add_argument("--authority", action="append", default=[])
    parser.add_argument(
        "--approval-token", default="DIALOGUE_TRANSLATION_APPROVED"
    )
    parser.add_argument("--supersede-approved", action="store_true")
    parser.add_argument("--supersede-reason")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if bool(args.translation_id) != bool(args.suggested_text):
        parser.error("--translation-id and --suggested-text must be provided together")
    if bool(args.supersede_approved) != bool(args.supersede_reason):
        parser.error(
            "--supersede-approved and --supersede-reason must be provided together"
        )
    suggestions = (
        {str(args.translation_id): str(args.suggested_text)}
        if args.translation_id
        else None
    )
    with get_session_factory()() as db:
        payload = prepare_dialogue_translation_review(
            db,
            source_video_id=UUID(str(args.source_video_id)),
            root_dir=Path(args.root_dir),
            suggested_text_by_translation_id=suggestions,
            authority_paths=[Path(item) for item in args.authority],
            required_approval_token=str(args.approval_token),
            supersede_approved=bool(args.supersede_approved),
            supersede_reason=args.supersede_reason,
        )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "segments": len(payload["segments"]),
                "review_input_sha256": payload["review_input_sha256"],
                "artifact_sha256": payload["artifact_sha256"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
