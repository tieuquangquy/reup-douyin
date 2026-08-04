"""Run Master Phase 1 only (timeline + keyframes + QA). No OCR/translate/render."""

from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from pathlib import Path

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    PADDING,
    ROI_Y0,
    ROI_Y1,
    STEP,
    MasterPhase1Extractor,
)

API_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = (
    API_ROOT.parents[1]
    / ".douyin_profiles"
    / "download_staging"
    / "7657906958829468523.mp4"
)
DEFAULT_OUT = API_ROOT / "tmp_phase1_only_review"


def main(
    argv: list[str] | None = None,
    *,
    on_progress=None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    step = STEP
    positional: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in {"--step", "-s"} and i + 1 < len(args):
            step = max(1, int(args[i + 1]))
            i += 2
            continue
        positional.append(args[i])
        i += 1
    video = Path(positional[0]) if positional else DEFAULT_VIDEO
    out = Path(positional[1]) if len(positional) > 1 else DEFAULT_OUT
    pad = step  # keep pad == step (fade coverage between samples)

    if on_progress is None:
        def on_progress(phase: str, current: int, total: int) -> None:
            print(f"[P1_PROGRESS] {phase} {current} {total}", flush=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("onnxruntime").setLevel(logging.ERROR)

    if not video.is_file():
        print(f"[FAIL] video missing: {video}", flush=True)
        return 1

    resumable_checkpoint = out / ".phase1_scan_checkpoint.json"
    if out.exists() and not resumable_checkpoint.is_file():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[P1] video={video}", flush=True)
    print(f"[P1] out={out.resolve()}", flush=True)
    print(f"[P1] STEP={step} ROI=[{ROI_Y0},{ROI_Y1}] PAD={pad}", flush=True)

    t0 = time.perf_counter()
    result = MasterPhase1Extractor(
        step=step,
        pad=pad,
        on_progress=on_progress,
    ).extract(video, out)
    elapsed = time.perf_counter() - t0

    keyframes = len(list(result.frames_dir.glob("*.jpg")))
    qa_dir = out / "qa"
    crops_dir = out / "crops"
    qa_n = len(list(qa_dir.glob("*.jpg"))) if qa_dir.is_dir() else 0
    crop_n = len(list(crops_dir.glob("*.jpg"))) if crops_dir.is_dir() else 0

    meta = {
        "video": str(video),
        "out": str(out.resolve()),
        "tracks": len(result.timeline),
        "frame_count": result.frame_count,
        "fps": result.fps,
        "step": step,
        "pad": pad,
        "roi_y0": ROI_Y0,
        "roi_y1": ROI_Y1,
        "keyframes": keyframes,
        "qa_overlays": qa_n,
        "crops": crop_n,
        "elapsed_s": round(elapsed, 2),
        "timeline_path": str(result.timeline_path),
    }
    (out / "phase1_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[P1] tracks={len(result.timeline)} frames={result.frame_count} "
        f"fps={result.fps:.3f} keyframes={keyframes} qa={qa_n} crops={crop_n}",
        flush=True,
    )
    coverage_path = out / "text_frame_coverage.json"
    if coverage_path.is_file():
        cov = json.loads(coverage_path.read_text(encoding="utf-8"))
        meta["n_frames_with_text"] = cov.get("n_frames_with_text")
        meta["n_scanned_frames"] = cov.get("n_scanned_frames")
        meta["coverage_path"] = str(coverage_path.resolve())
        (out / "phase1_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[P1] text_coverage frames_with_text={cov.get('n_frames_with_text')}/"
            f"{result.frame_count} scanned={cov.get('n_scanned_frames')} "
            f"hits={cov.get('n_hits')}",
            flush=True,
        )
        print(f"[P1] coverage={coverage_path.resolve()}", flush=True)
    print(f"[P1] timeline={result.timeline_path}", flush=True)
    print(f"[P1] DONE elapsed_s={elapsed:.1f}", flush=True)
    if result.timeline:
        first = result.timeline[0]
        print(
            "[P1] first="
            + json.dumps(
                {
                    k: first.get(k)
                    for k in (
                        "text_id",
                        "start_time",
                        "end_time",
                        "start_frame",
                        "end_frame",
                    )
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
