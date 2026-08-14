"""Probe outlined white/yellow editor-caption rows on selected source frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def rows(frame: np.ndarray) -> list[dict[str, float]]:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    spread = np.max(frame, axis=2).astype(np.int16) - np.min(frame, axis=2).astype(np.int16)
    white = (gray >= 165) & (spread <= 100)
    b, g, r = cv2.split(frame)
    yellow = (r >= 145) & (g >= 125) & (b <= 145) & ((r.astype(np.int16) - b.astype(np.int16)) >= 35)
    dark = gray <= 105
    near_dark = cv2.dilate(
        dark.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
        iterations=1,
    ) > 0
    candidate = ((white | yellow) & near_dark).astype(np.uint8)
    candidate[: int(height * 0.40), :] = 0
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(candidate, 8)
    glyphs: list[tuple[int, int, int, int, float, float, int]] = []
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        if 2 <= w <= int(width * 0.16) and 4 <= h <= int(height * 0.10) and area >= 8:
            glyphs.append((x, y, w, h, float(centroids[index][0]), float(centroids[index][1]), area))
    if not glyphs:
        return []
    # Baseline graph: outlined glyph fills on one editor row have overlapping
    # vertical extents.  Connected components may split a Chinese character,
    # so group components transitively before applying row evidence.
    neighbors: list[set[int]] = [set() for _ in glyphs]
    for i, left in enumerate(glyphs):
        ly0, ly1 = left[1], left[1] + left[3]
        for j, right in enumerate(glyphs[i + 1 :], start=i + 1):
            ry0, ry1 = right[1], right[1] + right[3]
            overlap = max(0, min(ly1, ry1) - max(ly0, ry0))
            smaller = min(left[3], right[3])
            if smaller and (overlap / smaller >= 0.25 or abs(left[5] - right[5]) <= max(left[3], right[3]) * 0.55):
                neighbors[i].add(j)
                neighbors[j].add(i)
    groups: list[list[tuple[int, int, int, int, float, float, int]]] = []
    visited: set[int] = set()
    for seed in range(len(glyphs)):
        if seed in visited:
            continue
        pending = [seed]
        component: list[int] = []
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            pending.extend(neighbors[current])
        groups.append([glyphs[index] for index in component])
    output: list[dict[str, float]] = []
    for group in groups:
        x0 = min(value[0] for value in group)
        y0 = min(value[1] for value in group)
        x1 = max(value[0] + value[2] for value in group)
        y1 = max(value[1] + value[3] for value in group)
        span = x1 - x0
        if len(group) < 3 or span < width * 0.10 or sum(value[6] for value in group) < 80:
            continue
        output.append(
            {
                "x": x0 / width,
                "y": y0 / height,
                "width": span / width,
                "height": (y1 - y0) / height,
                "components": len(group),
            }
        )
    return sorted(output, key=lambda value: (value["y"], value["x"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("frames")
    args = parser.parse_args()
    root = args.root.resolve()
    meta = json.loads((root / "phase1_meta.json").read_text(encoding="utf-8"))
    source = Path(str(meta["video"]))
    wanted = {int(value) for value in args.frames.split(",") if value.strip()}
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError("Cannot open source")
    results: dict[int, list[dict[str, float]]] = {}
    index = 0
    try:
        while wanted:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if index in wanted:
                results[index] = rows(frame)
                wanted.remove(index)
            index += 1
    finally:
        capture.release()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
