"""Phase 2: Video OCR + subtitle-band filtering (bottom 1/3 only)."""

from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.subtitle_band import BOTTOM_BAND_RATIO, filter_subtitle_band_boxes
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrFilterResult, OcrFilteringResult

__all__ = [
    "BOTTOM_BAND_RATIO",
    "DetectedTextBox",
    "FrameOcrFilterResult",
    "OcrFilteringResult",
    "filter_subtitle_band_boxes",
    "run_ocr_filtering",
]
