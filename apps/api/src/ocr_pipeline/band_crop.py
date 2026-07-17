"""Hard-sub band crop helpers for faster OCR on the bottom band only."""

from __future__ import annotations

from pathlib import Path

from src.ocr_pipeline.types import DEFAULT_HARD_SUB_BAND_RATIO, OcrBox


def band_crop_top_ratio(band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO) -> float:
    ratio = max(0.05, min(0.6, float(band_ratio)))
    return 1.0 - ratio


def remap_box_from_band_crop(box: OcrBox, *, band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO) -> OcrBox:
    """Map a box detected on a bottom-band crop back into full-frame normalized coords."""
    top = band_crop_top_ratio(band_ratio)
    height_scale = max(0.05, min(0.6, float(band_ratio)))
    return OcrBox(
        x=box.x,
        y=top + (box.y * height_scale),
        width=box.width,
        height=max(0.01, box.height * height_scale),
        text=box.text,
        confidence=box.confidence,
    )


def crop_bottom_band_image(
    image_path: Path,
    output_path: Path,
    *,
    band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO,
) -> tuple[int, int, int]:
    """Crop the bottom hard-sub band to `output_path`.

    Returns (full_width, full_height, crop_top_px).
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for OCR band crop") from exc

    with Image.open(image_path) as img:
        width, height = img.size
        top_px = int(round(height * band_crop_top_ratio(band_ratio)))
        top_px = max(0, min(height - 1, top_px))
        cropped = img.crop((0, top_px, width, height))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output_path, quality=95)
    return width, height, top_px
