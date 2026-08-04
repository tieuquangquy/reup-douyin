"""Retry Demucs stems without rerunning ASR/translation."""

from __future__ import annotations

import argparse
import json
import sys
from uuid import UUID

from src.audio_pipeline.services.background_recovery_service import (
    BackgroundRecoveryError,
    BackgroundRecoveryService,
)
from src.db.session import get_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.recover_background_stem")
    parser.add_argument("source_video_id")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        with get_session_factory()() as db:
            result = BackgroundRecoveryService(db).recover(
                UUID(str(args.source_video_id))
            )
    except BackgroundRecoveryError as exc:
        print(json.dumps({"status": "FAIL", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": "PASS", **result.to_dict()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
