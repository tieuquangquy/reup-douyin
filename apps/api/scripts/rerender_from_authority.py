"""Re-render final video from saved ocr_authority.json (skip V3)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("TRANSLATE_LLM_DRY", "1")

from src.media_pipeline.translator.service import translate_subtitles
from src.media_pipeline.video_renderer.renderer import render_video_single_pass

ROOT = API_ROOT / "tmp_e2e_authority_product"
REPO = API_ROOT.parents[1]
VIDEO = next(
    (REPO / "data" / "storage").rglob("*7657906958829468523*.mp4"),
    None,
)
if VIDEO is None:
    raise SystemExit("video not found")


def main() -> int:
    auth = json.loads((ROOT / "ocr_authority.json").read_text(encoding="utf-8"))
    vi = translate_subtitles(auth)
    (ROOT / "vi_texts.json").write_text(
        json.dumps(vi, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    real = sum(1 for v in vi.values() if v not in ("...", ""))
    print(f"vi_real={real} of={len(vi)}", flush=True)
    out = ROOT / "final_complete.mp4"
    render_video_single_pass(VIDEO, out, ocr_payload=auth, vi_texts=vi)
    print(f"OK {out} size={out.stat().st_size}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
