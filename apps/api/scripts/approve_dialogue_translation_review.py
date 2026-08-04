"""Apply an explicit operator dialogue-translation approval token."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from src.audio_pipeline.services.dialogue_translation_review import (
    DialogueTranslationReviewError,
    approve_dialogue_translation_review,
)
from src.db.session import get_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_dialogue_translation_review"
    )
    parser.add_argument("source_video_id")
    parser.add_argument("root_dir")
    parser.add_argument("approval_token")
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        with get_session_factory()() as db:
            result = approve_dialogue_translation_review(
                db,
                source_video_id=UUID(str(args.source_video_id)),
                root_dir=Path(args.root_dir),
                approval_token=str(args.approval_token),
                operator_id=str(args.operator),
            )
    except (OSError, json.JSONDecodeError, DialogueTranslationReviewError) as exc:
        print(json.dumps({"status": "FAIL", "message": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "segments": len(result["segments"]),
                "approval_sha256": result["approval_sha256"],
                "tts_synthesis_triggered": result["tts_synthesis_triggered"],
                "audio_approval_written": result["audio_approval_written"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
