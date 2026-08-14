"""Score Analyze Audio outputs against an offline labelled JSON corpus.

Manifest shape:
{"cases": [{"id": "clip-1", "reference": {"text": "...", "intervals": [[0, 1]]},
             "prediction": {"text": "...", "intervals": [[0, 1]]}}]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.audio_pipeline.quality_metrics import evaluate_audio_quality


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--max-cer", type=float, default=None)
    parser.add_argument("--max-wer", type=float, default=None)
    parser.add_argument("--min-timing-iou", type=float, default=None)
    parser.add_argument("--max-false-dialogue-rate", type=float, default=None)
    parser.add_argument("--max-missed-dialogue-rate", type=float, default=None)
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for case in list(payload.get("cases") or []):
        reference = dict(case.get("reference") or {})
        prediction = dict(case.get("prediction") or {})
        metrics = evaluate_audio_quality(
            reference_text=str(reference.get("text") or ""),
            predicted_text=str(prediction.get("text") or ""),
            reference_intervals=list(reference.get("intervals") or []),
            predicted_intervals=list(prediction.get("intervals") or []),
        )
        rows.append({"id": str(case.get("id") or ""), **metrics.to_dict()})
    keys = ("cer", "wer", "timing_iou", "false_dialogue_rate", "missed_dialogue_rate")
    aggregate = {
        key: round(sum(float(row[key]) for row in rows) / len(rows), 6) if rows else None
        for key in keys
    }
    thresholds = {
        "cer": args.max_cer,
        "wer": args.max_wer,
        "timing_iou_min": args.min_timing_iou,
        "false_dialogue_rate": args.max_false_dialogue_rate,
        "missed_dialogue_rate": args.max_missed_dialogue_rate,
    }
    failures: list[str] = []
    for key, limit in thresholds.items():
        if limit is None:
            continue
        if key == "timing_iou_min":
            if aggregate["timing_iou"] is not None and aggregate["timing_iou"] < limit:
                failures.append(f"timing_iou<{limit}")
        elif aggregate[key] is not None and aggregate[key] > limit:
            failures.append(f"{key}>{limit}")
    report = {
        "schema_version": "audio-benchmark-report-v1",
        "status": "PASS" if rows and not failures else "FAIL",
        "case_count": len(rows),
        "aggregate": aggregate,
        "thresholds": thresholds,
        "threshold_failures": failures,
        "cases": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if rows and not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
