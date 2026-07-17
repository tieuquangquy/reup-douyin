"""
Local smoke demo for Single Render (Phase 3+4).

Usage (from apps/api):
  python -m src.media_pipeline.video_renderer
  python -m src.media_pipeline.video_renderer --video path\\to\\clip.mp4

If --video is omitted, generates a short synthetic MP4 via lavfi, then renders.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from src.media_pipeline.video_renderer.overlays import OverlaySegment
from src.media_pipeline.video_renderer.renderer import render_video_single_pass


def _make_synthetic_clip(path: Path, *, seconds: float = 3.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found on PATH — install FFmpeg to run this demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=gray:s=640x360:d={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not path.is_file():
        raise SystemExit(f"Failed to create synthetic clip: {completed.stderr[:400]}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3+4 Single Render demo")
    parser.add_argument("--video", type=Path, default=None, help="Input MP4 (optional)")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output MP4 (default: .tmp/video_renderer_demo/out_single_pass.mp4)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Anti-detection RNG seed")
    args = parser.parse_args(argv)

    demo_root = Path(__file__).resolve().parents[3] / ".tmp" / "video_renderer_demo"
    demo_root.mkdir(parents=True, exist_ok=True)

    if args.video is not None:
        source = args.video
        if not source.is_file():
            print(f"Video not found: {source}", file=sys.stderr)
            return 2
    else:
        source = demo_root / "synthetic_in.mp4"
        print(f"No --video given; generating synthetic clip -> {source}")
        _make_synthetic_clip(source)

    output = args.out or (demo_root / "out_single_pass.mp4")

    # Hardcoded mock boxes (normalized) + Vietnamese — mimics Phase 2 bottom-band output.
    overlays = [
        OverlaySegment(
            start_ms=0,
            end_ms=1500,
            x=0.08,
            y=0.78,
            width=0.84,
            height=0.14,
            text_vi="Xin chao — phu de dich (mock)",
        ),
        OverlaySegment(
            start_ms=1500,
            end_ms=3000,
            x=0.12,
            y=0.80,
            width=0.76,
            height=0.12,
            text_vi="Single Render: mask + VI + anti-hash",
        ),
    ]

    print(f"source : {source}")
    print(f"output : {output}")
    print(f"overlays: {len(overlays)} (mock VI)")
    try:
        render_video_single_pass(
            source,
            output,
            overlays,
            anti_seed=args.seed,
            progress=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"RENDER FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"OK -> {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
