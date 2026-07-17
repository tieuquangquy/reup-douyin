"""Subtitle-band geometry: keep OCR boxes only in the bottom 1/3 of the frame."""

from __future__ import annotations

from pathlib import Path

from src.media_pipeline.ocr_filtering.types import DetectedTextBox, Vertex

# STRICT product rule: only the lower third is treated as the hard-sub / subtitle zone.
BOTTOM_BAND_RATIO = 1.0 / 3.0


def clamp_band_ratio(band_ratio: float) -> float:
    return max(0.05, min(0.5, float(band_ratio)))


def subtitle_band_top_normalized(band_ratio: float = BOTTOM_BAND_RATIO) -> float:
    """Normalized Y where the subtitle band begins (top of bottom third)."""
    return 1.0 - clamp_band_ratio(band_ratio)


def is_in_subtitle_band(box: DetectedTextBox, *, band_ratio: float = BOTTOM_BAND_RATIO) -> bool:
    """True when the box center lies in the bottom `band_ratio` of the frame.

    Top 2/3 (logos, clothing text, signage) are rejected.
    """
    # Tiny epsilon avoids float edge cases exactly on the 2/3 boundary.
    return box.center_y + 1e-9 >= subtitle_band_top_normalized(band_ratio)


def filter_subtitle_band_boxes(
    boxes: list[DetectedTextBox],
    *,
    band_ratio: float = BOTTOM_BAND_RATIO,
) -> list[DetectedTextBox]:
    """Return only boxes whose center is inside the bottom subtitle band."""
    return [box for box in boxes if is_in_subtitle_band(box, band_ratio=band_ratio)]


def band_crop_pixel_box(
    width: int,
    height: int,
    *,
    band_ratio: float = BOTTOM_BAND_RATIO,
) -> tuple[int, int, int, int]:
    """Return PIL-style (left, top, right, bottom) for the bottom subtitle band."""
    ratio = clamp_band_ratio(band_ratio)
    top = max(0, min(height - 1, int(round(height * (1.0 - ratio)))))
    return 0, top, int(width), int(height)


def remap_box_from_band_crop(
    box: DetectedTextBox,
    *,
    band_ratio: float = BOTTOM_BAND_RATIO,
) -> DetectedTextBox:
    """Map a box normalized to the band crop back into full-frame coordinates."""
    ratio = clamp_band_ratio(band_ratio)
    y0 = subtitle_band_top_normalized(ratio)
    vertices = tuple(
        Vertex(x=v.x, y=y0 + v.y * ratio) for v in box.vertices
    )
    return DetectedTextBox(
        x=box.x,
        y=y0 + box.y * ratio,
        width=box.width,
        height=box.height * ratio,
        text=box.text,
        confidence=box.confidence,
        vertices=vertices,
    )


def crop_bottom_band_jpeg(
    source: Path,
    destination: Path,
    *,
    band_ratio: float = BOTTOM_BAND_RATIO,
) -> tuple[int, int, int]:
    """Crop bottom band to ``destination`` JPEG.

    Returns ``(full_width, full_height, crop_height)``.
    """
    from PIL import Image  # type: ignore

    source = Path(source)
    destination = Path(destination)
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        left, top, right, bottom = band_crop_pixel_box(width, height, band_ratio=band_ratio)
        cropped = rgb.crop((left, top, right, bottom))
        destination.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(destination, format="JPEG", quality=90)
        return width, height, int(cropped.size[1])
