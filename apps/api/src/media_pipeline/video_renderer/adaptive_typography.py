"""Responsive Vietnamese typography constrained by explicit safe areas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_UNITS = {"g", "kg", "mg", "ml", "l", "kcal", "%", "muỗng"}
_BASE_FRAC = {
    "hardsub": 0.040,
    "title": 0.045,
    "ui": 0.032,
    "caption_row": 0.028,
    "micro_ui": 0.019,
}
_MIN_FRAC = {
    "hardsub": 0.026,
    "title": 0.030,
    "ui": 0.022,
    "caption_row": 0.018,
    "micro_ui": 0.014,
}

# Recipe-visible contract for the source-relative dense panel layout.  Keeping
# this explicit prevents a future renderer from silently reverting to a full
# safe-area grid and spreading one compact source group apart.
DENSE_GROUP_LAYOUT_POLICY_VERSION = "source_relative_dense_group_v1"


class TypographyLayoutError(RuntimeError):
    """Locked text cannot be laid out legibly inside its safe area."""


@dataclass(frozen=True)
class TextLayout:
    lines: tuple[str, ...]
    font_size_px: int
    x0: int
    y0: int
    width: int
    height: int
    fill_rgb: tuple[int, int, int]
    stroke_rgb: tuple[int, int, int]
    rgba: np.ndarray


def _safe_area_pixels(
    safe_area: Mapping[str, Any], *, frame_width: int, frame_height: int
) -> tuple[int, int, int, int]:
    try:
        x = float(safe_area.get("x") or 0.0)
        y = float(safe_area.get("y") or 0.0)
        width = float(safe_area.get("width") or 0.0)
        height = float(safe_area.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise TypographyLayoutError("Safe area must be numeric") from exc
    x0 = max(0, min(frame_width, int(round(x * frame_width))))
    y0 = max(0, min(frame_height, int(round(y * frame_height))))
    x1 = max(x0, min(frame_width, int(round((x + width) * frame_width))))
    y1 = max(y0, min(frame_height, int(round((y + height) * frame_height))))
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise TypographyLayoutError("Text safe area is too small")
    return x0, y0, x1, y1


def _protected_words(text: str) -> list[str]:
    words = [part for part in str(text or "").strip().split() if part]
    output: list[str] = []
    index = 0
    while index < len(words):
        current = words[index]
        if (
            _NUMBER_RE.match(current)
            and index + 1 < len(words)
            and words[index + 1].casefold() in _UNITS
        ):
            output.append(f"{current} {words[index + 1]}")
            index += 2
        else:
            output.append(current)
            index += 1
    return output


def _line_size(draw: Any, line: str, font: Any, *, stroke: int) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
    return max(1, bbox[2] - bbox[0] + 4), max(1, bbox[3] - bbox[1] + 4)


def _candidate_lines(
    text: str, *, max_lines: int, draw: Any, font: Any, stroke: int
) -> list[tuple[str, ...]]:
    words = _protected_words(text)
    if not words:
        return []
    candidates: list[tuple[str, ...]] = [(" ".join(words),)]
    if max_lines >= 2 and len(words) >= 2:
        splits: list[tuple[float, tuple[str, ...]]] = []
        for index in range(1, len(words)):
            first = " ".join(words[:index])
            second = " ".join(words[index:])
            width_a, _ = _line_size(draw, first, font, stroke=stroke)
            width_b, _ = _line_size(draw, second, font, stroke=stroke)
            splits.append((abs(width_a - width_b), (first, second)))
        candidates.extend(lines for _score, lines in sorted(splits, key=lambda item: item[0]))
    return candidates


def _colors(background_bgr: np.ndarray, bounds: tuple[int, int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    x0, y0, x1, y1 = bounds
    roi = background_bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return (255, 255, 255), (0, 0, 0)
    mean = roi.reshape(-1, 3).mean(axis=0)
    luma = float(0.114 * mean[0] + 0.587 * mean[1] + 0.299 * mean[2])
    if luma >= 140.0:
        return (28, 28, 28), (245, 245, 245)
    return (255, 255, 255), (0, 0, 0)


def _rasterize(
    lines: tuple[str, ...],
    *,
    font: Any,
    draw_probe: Any,
    stroke: int,
    fill_rgb: tuple[int, int, int],
    stroke_rgb: tuple[int, int, int],
) -> tuple[np.ndarray, int, int]:
    from PIL import Image, ImageDraw

    sizes = [_line_size(draw_probe, line, font, stroke=stroke) for line in lines]
    gap = max(2, int(round(getattr(font, "size", 12) * 0.16))) if len(lines) > 1 else 0
    width = max(size[0] for size in sizes)
    height = sum(size[1] for size in sizes) + gap * (len(lines) - 1)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = 0
    for line, (line_width, line_height) in zip(lines, sizes):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        x = (width - line_width) // 2
        draw.text(
            (x - bbox[0] + 2, y - bbox[1] + 2),
            line,
            font=font,
            fill=(*fill_rgb, 255),
            stroke_width=stroke,
            stroke_fill=(*stroke_rgb, 255),
        )
        y += line_height + gap
    return np.asarray(image, dtype=np.uint8).copy(), width, height


def plan_text_layout(
    text: str,
    *,
    kind: str,
    safe_area: Mapping[str, Any],
    frame_width: int,
    frame_height: int,
    fontfile: Path | str,
    background_bgr: np.ndarray,
    max_lines: int,
) -> TextLayout:
    from PIL import Image, ImageDraw, ImageFont

    raw = str(text or "").strip()
    if not raw:
        raise TypographyLayoutError("Vietnamese text is empty")
    normalized_kind = kind if kind in _BASE_FRAC else "ui"
    x0, y0, x1, y1 = _safe_area_pixels(
        safe_area, frame_width=frame_width, frame_height=frame_height
    )
    available_width = x1 - x0
    available_height = y1 - y0
    base = max(12, int(round(frame_height * _BASE_FRAC[normalized_kind])))
    minimum = max(12, int(round(frame_height * _MIN_FRAC[normalized_kind])))
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    stroke = 2 if frame_height >= 360 else 1
    chosen: tuple[tuple[str, ...], Any, np.ndarray, int, int] | None = None
    fill, outline = _colors(background_bgr, (x0, y0, x1, y1))
    for size in range(base, minimum - 1, -1):
        try:
            font = ImageFont.truetype(str(fontfile), size=size)
        except OSError as exc:
            raise TypographyLayoutError("Cannot load typography font") from exc
        for candidate in _candidate_lines(
            raw,
            max_lines=max(1, int(max_lines)),
            draw=probe,
            font=font,
            stroke=stroke,
        ):
            if len(candidate) > max(1, int(max_lines)):
                continue
            rgba, width, height = _rasterize(
                candidate,
                font=font,
                draw_probe=probe,
                stroke=stroke,
                fill_rgb=fill,
                stroke_rgb=outline,
            )
            if width <= available_width and height <= available_height:
                chosen = candidate, font, rgba, width, height
                break
        if chosen is not None:
            break
    if chosen is None:
        raise TypographyLayoutError(
            "Locked Vietnamese text does not fit its safe area within font limits"
        )
    lines, font, rgba, width, height = chosen
    place_x = x0 + max(0, (available_width - width) // 2)
    place_y = y0 + max(0, (available_height - height) // 2)
    return TextLayout(
        lines=lines,
        font_size_px=int(font.size),
        x0=place_x,
        y0=place_y,
        width=width,
        height=height,
        fill_rgb=fill,
        stroke_rgb=outline,
        rgba=rgba,
    )


def plan_dense_grid_layouts(
    items: Sequence[Mapping[str, Any]],
    *,
    safe_area: Mapping[str, Any],
    frame_width: int,
    frame_height: int,
    fontfile: Path | str,
    background_bgr: np.ndarray,
) -> list[dict[str, Any]]:
    area_x0, area_y0, area_x1, area_y1 = _safe_area_pixels(
        safe_area, frame_width=frame_width, frame_height=frame_height
    )
    left = [dict(item) for item in items if str(item.get("side") or "left") == "left"]
    right = [dict(item) for item in items if str(item.get("side") or "left") != "left"]
    gap = max(12, int(round(frame_width * 0.04)))
    total_width = area_x1 - area_x0
    column_width = max(20, (total_width - gap) // 2)

    def _source_relative_bounds(
        column: Sequence[Mapping[str, Any]],
    ) -> dict[str, tuple[int, int]] | None:
        """Return compact source-relative row cells when geometry is available.

        Dense UI used to spread every row over the complete safe area.  That is
        appropriate for an unknown dashboard, but it visibly stretches a
        single editor-authored group.  Use the source y centers and the source
        group bounding box instead, preserving the spacing while still giving
        each translated label a collision-safe cell.
        """

        source_rows: list[tuple[str, float, float, float]] = []
        for item in column:
            geometry = item.get("geometry")
            if not isinstance(geometry, Mapping):
                return None
            text_id = str(item.get("text_id") or "")
            if not text_id:
                return None
            y = float(geometry.get("y") or 0.0)
            height = float(geometry.get("height") or 0.0)
            if not 0.0 <= y < 1.0 or height <= 0.0 or y + height > 1.0:
                return None
            source_rows.append((text_id, y, height, y + height * 0.5))
        if len(source_rows) < 2:
            return None
        stable_rows = [
            row
            for row in column
            if isinstance(row.get("stable_slot"), Mapping)
        ]
        if len(stable_rows) == len(column):
            order = {
                str(row.get("text_id") or ""): int(
                    dict(row.get("stable_slot") or {}).get("slot_index") or 0
                )
                for row in stable_rows
            }
            source_rows.sort(key=lambda row: (order[row[0]], row[1], row[0]))
        else:
            source_rows.sort(key=lambda row: (row[1], row[0]))
        group_y0 = min(row[1] for row in source_rows)
        group_y1 = max(row[1] + row[2] for row in source_rows)
        if group_y1 <= group_y0:
            return None
        min_cell_height = max(24, int(round(frame_height * 0.05)))
        bounds: dict[str, tuple[int, int]] = {}
        for index, (text_id, y, height, center) in enumerate(source_rows):
            previous_center = source_rows[index - 1][3] if index else None
            next_center = source_rows[index + 1][3] if index + 1 < len(source_rows) else None
            cell_y0 = group_y0 if previous_center is None else (previous_center + center) * 0.5
            cell_y1 = group_y1 if next_center is None else (center + next_center) * 0.5
            y0 = max(area_y0, min(area_y1, int(round(cell_y0 * frame_height))))
            y1 = max(y0 + 8, min(area_y1, int(round(cell_y1 * frame_height))))
            if y1 <= y0 or y1 - y0 < min_cell_height:
                # A source-relative cell that is too short would force the
                # typography planner to shrink or reject locked Vietnamese.
                # Let the caller use its capacity-safe grid in that case.
                return None
            bounds[text_id] = (y0, y1)
        return bounds

    def _layout_columns(
        columns: tuple[list[dict[str, Any]], list[dict[str, Any]]],
        *,
        placement_mode: str,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for column_index, column in enumerate(columns):
            if not column:
                continue
            column_x = area_x0 + column_index * (column_width + gap)
            stable_items = [
                item for item in column if isinstance(item.get("stable_slot"), Mapping)
            ]
            stable_count = max(
                [
                    int(dict(item.get("stable_slot") or {}).get("slot_count") or 0)
                    for item in stable_items
                ]
                or [0]
            )
            use_stable_slots = bool(stable_items) and len(stable_items) == len(column)
            row_count = stable_count if use_stable_slots else len(column)
            row_height = max(8, (area_y1 - area_y0) // max(1, row_count))
            ordered_column = (
                sorted(
                    column,
                    key=lambda item: (
                        int(dict(item.get("stable_slot") or {}).get("slot_index") or 0),
                        str(item.get("text_id") or ""),
                    ),
                )
                if use_stable_slots
                else column
            )
            source_bounds = (
                _source_relative_bounds(ordered_column)
                if use_stable_slots
                else None
            )
            effective_placement_mode = (
                "source_relative" if source_bounds is not None else placement_mode
            )
            for row_index, item in enumerate(ordered_column):
                if use_stable_slots:
                    row_index = int(
                        dict(item.get("stable_slot") or {}).get("slot_index")
                        or 0
                    )
                cell_x0 = column_x
                if source_bounds is not None:
                    cell_y0, cell_y1 = source_bounds[str(item.get("text_id") or "")]
                else:
                    cell_y0 = area_y0 + row_index * row_height
                    cell_y1 = (
                        area_y1
                        if row_index == len(column) - 1
                        else cell_y0 + row_height
                    )
                cell = {
                    "x": cell_x0 / frame_width,
                    "y": cell_y0 / frame_height,
                    "width": column_width / frame_width,
                    "height": max(1, cell_y1 - cell_y0) / frame_height,
                }
                layout = plan_text_layout(
                    str(item.get("text") or ""),
                    kind="ui",
                    safe_area=cell,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    fontfile=fontfile,
                    background_bgr=background_bgr,
                    max_lines=1,
                )
                output.append(
                    {
                        **item,
                        "layout": layout,
                        "placement_mode": effective_placement_mode,
                    }
                )
        return output

    try:
        return _layout_columns((left, right), placement_mode="source_side")
    except TypographyLayoutError as source_side_error:
        # A narrow portrait app can place almost every source label on the
        # same half of the encoded frame. Preserve source-side placement when
        # it is legible, but fail over to capacity-balanced columns before
        # rejecting locked Vietnamese text. Font and safe-area limits remain
        # unchanged, so this cannot silently shrink or truncate content.
        balanced = [dict(item) for item in items]
        midpoint = (len(balanced) + 1) // 2
        balanced_columns = (balanced[:midpoint], balanced[midpoint:])
        if [len(left), len(right)] == [len(row) for row in balanced_columns]:
            raise source_side_error
        return _layout_columns(
            balanced_columns,
            placement_mode="balanced_capacity_fallback",
        )
