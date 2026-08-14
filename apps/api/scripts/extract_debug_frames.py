"""Extract exact decoded source/output frames for local regression diagnosis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


def _extract(video: Path, frames: set[int], output: Path) -> None:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    output.mkdir(parents=True, exist_ok=True)
    index = 0
    try:
        while frames:
            ok, image = capture.read()
            if not ok or image is None:
                break
            if index in frames:
                if not cv2.imwrite(str(output / f"frame_{index:04d}.jpg"), image):
                    raise RuntimeError(f"Cannot write frame {index}")
                frames.remove(index)
            index += 1
    finally:
        capture.release()
    if frames:
        raise RuntimeError(f"Missing frames: {sorted(frames)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("frames")
    args = parser.parse_args()
    root = args.root.resolve()
    meta = json.loads((root / "phase1_meta.json").read_text(encoding="utf-8"))
    source = Path(str(meta["video"]))
    indices = {int(value) for value in args.frames.split(",") if value.strip()}
    _extract(source, set(indices), root / "debug_source_frames")
    _extract(
        root / "phase4_adaptive_visual_preview.mp4",
        set(indices),
        root / "debug_qa_frames_exact",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
