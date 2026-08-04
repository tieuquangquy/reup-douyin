"""Run the durable TTS V2 service synchronously for a local operator fixture."""

from __future__ import annotations

import argparse
import json
import sys
from uuid import UUID

from src.db.session import get_session_factory
from src.tts_pipeline.errors import TtsPipelineError
from src.tts_pipeline.services.tts_service import TtsPipelineService
from src.tts_pipeline.types import TtsRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.run_tts_v2_once")
    parser.add_argument("source_video_id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    source_video_id = UUID(str(args.source_video_id))
    with get_session_factory()() as db:
        try:
            result = TtsPipelineService(db).run_pipeline(
                TtsRequest(
                    source_video_id=source_video_id,
                    force_refresh=bool(args.force),
                )
            )
        except TtsPipelineError as exc:
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "code": str(exc.code),
                        "message": exc.message,
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
            return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "pipeline_version": result.pipeline_version,
                "clips": result.tts_clip_count,
                "fit": result.timing_fit_summary,
                "warnings": result.warnings,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
