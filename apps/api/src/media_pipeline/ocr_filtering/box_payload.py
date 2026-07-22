"""Normalize OCR box dict keys (width/height vs w/h) for render + persistence."""

from __future__ import annotations

from typing import Any, Mapping


def box_norm_xywh(box: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Return normalized x, y, width, height accepting either key style."""
    x = float(box.get("x") or 0.0)
    y = float(box.get("y") or 0.0)
    if "w" in box:
        w = float(box.get("w") or 0.01)
    else:
        w = float(box.get("width") or 0.01)
    if "h" in box:
        h = float(box.get("h") or 0.01)
    else:
        h = float(box.get("height") or 0.01)
    return x, y, max(0.01, w), max(0.01, h)
