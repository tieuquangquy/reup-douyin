"""Inspect one adaptive-render frame with the production contract boundary.

This is intentionally read-only: it decodes one source frame, applies the same
runtime policy normalization as the video renderer, and prints fail-closed
diagnostics without writing or mutating pipeline artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2

from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
)
from src.media_pipeline.video_renderer.adaptive_video import (
    active_protected_source_regions_for_frame,
    active_tracks_for_frame,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    _resolve_phase1_source_path,
)
from src.media_pipeline.video_renderer.render_policy import (
    enforce_unified_editor_cover_contract,
)


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return payload


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("frame_index", type=int)
    args = parser.parse_args()

    root = args.root.resolve()
    contract = enforce_unified_editor_cover_contract(
        _load_json(root / "phase4_render_input.json")
    )
    phase1_meta = _load_json(root / "phase1_meta.json")
    source = _resolve_phase1_source_path(root, str(phase1_meta["video"]))

    capture = cv2.VideoCapture(str(source))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, args.frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"Cannot decode source frame {args.frame_index}")

    active = active_tracks_for_frame(
        contract,
        args.frame_index,
        source_frame_bgr=frame,
    )
    protected = active_protected_source_regions_for_frame(
        contract, args.frame_index
    )
    renderer = AdaptiveFrameRenderer()
    renderer.seed_dense_layout_authority(list(contract.get("render_tracks") or []))
    renderer.seed_cover_component_authority(
        list(contract.get("render_tracks") or [])
    )

    summary = {
        "frame_index": args.frame_index,
        "source": str(source),
        "shape": list(frame.shape),
        "active_text_ids": [str(row.get("text_id") or "") for row in active],
        "protected_text_ids": [
            str(row.get("text_id") or "") for row in protected
        ],
        "canonical_component_rois": renderer._cover_component_rois,
    }
    try:
        _output, qa = renderer.render_frame(
            frame,
            active,
            frame_index=args.frame_index,
            protected_source_regions=protected,
        )
    except AdaptiveRenderBlocked as exc:
        summary["status"] = "BLOCKED"
        summary["error"] = str(exc)
        summary["diagnostics"] = exc.diagnostics
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2
    summary["status"] = "PASS"
    summary["diagnostics"] = qa
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
