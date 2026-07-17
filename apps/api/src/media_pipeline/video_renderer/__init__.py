"""Phase 3+4: Single Render — mask Chinese subs, burn Vietnamese, anti-hash (one FFmpeg pass)."""

from src.media_pipeline.video_renderer.filter_graph import (
    build_anti_detection_filters,
    build_single_render_filter,
    wrap_filter_complex,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment, overlays_from_ocr_payload
from src.media_pipeline.video_renderer.renderer import render_video_single_pass

__all__ = [
    "OverlaySegment",
    "build_anti_detection_filters",
    "build_single_render_filter",
    "overlays_from_ocr_payload",
    "render_video_single_pass",
    "wrap_filter_complex",
]
