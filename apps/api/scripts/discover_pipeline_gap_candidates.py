"""Scan trusted local source-video trees for real regression-gap candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_gap_discovery import (
    PipelineGapDiscoveryError,
    discover_gap_candidates,
    enumerate_source_videos,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.discover_pipeline_gap_candidates"
    )
    parser.add_argument("output_json")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--source-root", action="append", required=True)
    parser.add_argument("--max-duration", type=float, default=60.0)
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        corpus_path = Path(args.corpus).resolve()
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        gaps = corpus.get("real_video_gaps") if isinstance(corpus, dict) else None
        if not isinstance(gaps, dict) or not gaps:
            raise PipelineGapDiscoveryError("Corpus has no declared real-video gaps")
        paths, excluded = enumerate_source_videos(
            [Path(value) for value in args.source_root],
            workspace_root=WORKSPACE_ROOT,
        )
        payload = discover_gap_candidates(
            video_paths=paths,
            workspace_root=WORKSPACE_ROOT,
            target_gaps=gaps,
            max_duration_seconds=args.max_duration,
            excluded_source_count=len(excluded),
        )
        output = Path(args.output_json).resolve()
        if not output.is_relative_to(WORKSPACE_ROOT):
            raise PipelineGapDiscoveryError("Output must stay within workspace")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(output)
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "candidate_count": payload["candidate_count"],
                    "remaining_gaps": payload["remaining_gaps"],
                    "discovery_sha256": payload["discovery_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, PipelineGapDiscoveryError) as exc:
        print(f"[PIPELINE-GAP-DISCOVERY][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
