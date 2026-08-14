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
    # None preserves the legacy env-selected profile. Locked V24 queue runs set
    # True so worker execution cannot silently fall back to sparse sampling.
    use_master_phase1: bool | None = None
    # Callers must opt into the product quality workflow explicitly.  Keeping
    # the request default legacy prevents unrelated internal callers from being
    # silently migrated merely by constructing OcrRequest.
    workflow_version: str = "legacy_media_e2e_v1"
    workflow_action: str = "analyze"
    review_decisions: list[dict] = field(default_factory=list)
    operator_id: str = "frontend_operator"
    # Quality workflow callers opt into the local audio-visual temporal engine.
    # Legacy media-E2E callers keep V58 unless explicitly migrated.
    analysis_engine: str = "v58_candidate"
    # Full-auto queue jobs may promote only deterministic local review decisions.
    # Manual/frontend OCR requests keep the operator checkpoints by default.
    auto_advance: bool = False


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
