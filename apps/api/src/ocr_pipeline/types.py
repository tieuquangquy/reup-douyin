"""Hard-sub OCR pipeline types."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


OCR_PIPELINE_VERSION = "OCR_PIPELINE_V1"
# STRICT hard-sub sampling: exactly 1 or 2 fps (see media_pipeline.frame_sampling).
DEFAULT_SAMPLE_FPS = 1.0
DEFAULT_HARD_SUB_BAND_RATIO = 0.28
DEFAULT_MIN_STABLE_SAMPLES = 2


@dataclass(frozen=True)
class OcrBox:
    """Normalized bbox in [0, 1] relative to frame size."""

    x: float
    y: float
    width: float
    height: float
    text: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class FrameOcrResult:
    frame_time_ms: int
    frame_width: int
    frame_height: int
    boxes: list[OcrBox] = field(default_factory=list)


@dataclass(frozen=True)
class HardSubEvent:
    start_ms: int
    end_ms: int
    x: float
    y: float
    width: float
    height: float
    sample_count: int
    avg_confidence: float
    texts: list[str] = field(default_factory=list)
    unstable: bool = False


@dataclass(frozen=True)
class OcrRequest:
    source_video_id: UUID
    force_refresh: bool = False
    sample_fps: float = DEFAULT_SAMPLE_FPS
    hard_sub_band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO
    clean_hardsub: bool = True


@dataclass(frozen=True)
class OcrPipelineResult:
    pipeline_version: str
    source_video_id: str
    frame_count: int
    detection_count: int
    hardsub_event_count: int
    cleaned_video_asset_id: str | None
    warnings: list[str] = field(default_factory=list)
    hardsub_events: list[HardSubEvent] = field(default_factory=list)
    clean_produced: bool = False
