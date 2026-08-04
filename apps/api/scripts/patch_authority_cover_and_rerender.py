"""Patch saved authority: merge local_hardsub → cover_only, then re-render."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("TRANSLATE_LLM_DRY", "1")

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.ocr_authority_v3 import merge_local_cover_only
from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
    with_authority_cover_bounds,
)
from src.media_pipeline.translator.service import translate_subtitles
from src.media_pipeline.video_renderer.renderer import render_video_single_pass

ROOT = API_ROOT / "tmp_e2e_authority_product"
REPO = API_ROOT.parents[1]
VIDEO = next((REPO / "data" / "storage").rglob("*7657906958829468523*.mp4"), None)


def _as_timed(raw: dict) -> TimedBox:
    return TimedBox(
        x=float(raw.get("x") or 0.0),
        y=float(raw.get("y") or 0.0),
        w=float(raw.get("w") if "w" in raw else raw.get("width") or 0.0),
        h=float(raw.get("h") if "h" in raw else raw.get("height") or 0.0),
        text=str(raw.get("text") or ""),
        confidence=float(raw.get("confidence") or 0.0),
        cover_only=bool(raw.get("cover_only")),
        cover_bounds=(
            tuple(float(v) for v in raw["cover_bounds"])  # type: ignore[arg-type]
            if isinstance(raw.get("cover_bounds"), (list, tuple))
            and len(raw["cover_bounds"]) == 4
            else None
        ),
    )


def patch_authority(payload: dict) -> dict:
    frames = payload.get("frames") or []
    added = 0
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        approved = [_as_timed(b) for b in (frame.get("boxes") or []) if isinstance(b, dict)]
        local_raw = list(frame.get("local_hardsub_boxes") or [])
        local = [_as_timed(b) for b in local_raw if isinstance(b, dict)]
        before = len(approved)
        merged = [
            with_authority_cover_bounds(box)
            for box in merge_local_cover_only(approved, local)
        ]
        added += max(0, len(merged) - before)
        frame["boxes"] = [box.to_dict() for box in merged]
    print(f"cover_only_added={added}", flush=True)
    return payload


def main() -> int:
    if VIDEO is None or not VIDEO.is_file():
        raise SystemExit("video not found")
    path = ROOT / "ocr_authority.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = patch_authority(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    vi = translate_subtitles(payload)
    (ROOT / "vi_texts.json").write_text(
        json.dumps(vi, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out = ROOT / "final_complete.mp4"
    render_video_single_pass(VIDEO, out, ocr_payload=payload, vi_texts=vi)
    print(f"OK {out} size={out.stat().st_size}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
