"""Inspect selected local videos and build a deterministic regression corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_regression_corpus import (
    RegressionCorpusError,
    SUPPORTED_REGRESSION_VIDEO_EXTENSIONS,
    build_corpus_payload,
    classify_probe,
    load_phase1_metrics,
    probe_video,
    sample_visual_features,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def _resolve_selected_video(video_id: str, input_dirs: list[Path]) -> Path:
    for input_dir in input_dirs:
        root = input_dir.resolve()
        for extension in sorted(SUPPORTED_REGRESSION_VIDEO_EXTENSIONS):
            candidate = (root / f"{video_id}{extension}").resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
    raise RegressionCorpusError(f"Missing selected video: {video_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_pipeline_regression_corpus"
    )
    parser.add_argument("input_dir")
    parser.add_argument("output_json")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--additional-input-dir", action="append", default=[])
    parser.add_argument("--phase1-root", action="append", default=[])
    parser.add_argument("--max-duration", type=float, default=60.0)
    parser.add_argument(
        "--fresh-phase1",
        action="store_true",
        help=(
            "Use prior Phase-1 artifacts only to classify text density; force the "
            "regression runner to execute Phase 1 again from original source bytes."
        ),
    )
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        input_dirs = [
            Path(args.input_dir).resolve(),
            *(Path(value).resolve() for value in args.additional_input_dir),
        ]
        cases: list[dict[str, object]] = []
        for video_id in args.ids:
            video_path = _resolve_selected_video(video_id, input_dirs)
            probe = probe_video(video_path)
            if float(probe["duration_seconds"]) >= float(args.max_duration):
                raise RegressionCorpusError(f"Selected video is too long: {video_id}")
            visual = sample_visual_features(video_path)
            phase1 = load_phase1_metrics(video_id, list(args.phase1_root))
            dimensions = classify_probe(probe)
            dimensions["lighting"] = str(visual["lighting"])
            dimensions["motion"] = str(visual["motion"])
            dimensions["text_density"] = str(phase1["text_density"])
            cases.append(
                {
                    "case_id": f"local_{video_id}",
                    "source_video_external_id": video_id,
                    "status": "READY_FOR_BATCH_REGRESSION",
                    "video_path": video_path,
                    "phase1_artifact_root": (
                        None if args.fresh_phase1 else phase1["artifact_root"]
                    ),
                    "phase1_execution_policy": (
                        "FRESH_FROM_SOURCE"
                        if args.fresh_phase1
                        else "REUSE_ACCEPTED_BASELINE_ALLOWED"
                    ),
                    "probe": probe,
                    "visual_sample": visual,
                    "phase1_baseline": {
                        "track_count": phase1["track_count"],
                        "hardsub_count": phase1["hardsub_count"],
                    },
                    "dimensions": dimensions,
                }
            )
        payload = build_corpus_payload(
            cases=cases,
            workspace_root=WORKSPACE_ROOT,
        )
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(output_path)
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "case_count": payload["case_count"],
                    "corpus_sha256": payload["corpus_sha256"],
                    "gap_dimensions": sorted(payload["real_video_gaps"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RegressionCorpusError) as exc:
        print(f"[REGRESSION-CORPUS][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
