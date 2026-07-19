"""Types for Phase 2 OCR filtering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Vertex:
    """One corner of a text polygon (normalized 0–1 unless noted)."""

    x: float
    y: float


@dataclass(frozen=True)
class DetectedTextBox:
    """Axis-aligned box derived from OCR vertices (normalized to frame size)."""

    x: float
    y: float
    width: float
    height: float
    text: str = ""
    confidence: float = 0.0
    vertices: tuple[Vertex, ...] = ()

    @property
    def center_y(self) -> float:
        return self.y + (self.height / 2.0)

    @property
    def center_x(self) -> float:
        return self.x + (self.width / 2.0)


@dataclass(frozen=True)
class FrameOcrDetection:
    """Raw OCR output for one frame before subtitle-band filtering."""

    frame_width: int
    frame_height: int
    boxes: list[DetectedTextBox] = field(default_factory=list)


@dataclass(frozen=True)
class FrameOcrFilterResult:
    frame_id: str
    path: str
    time_ms: int
    frame_width: int
    frame_height: int
    boxes: list[DetectedTextBox] = field(default_factory=list)
    raw_box_count: int = 0
    filtered_out_count: int = 0


@dataclass(frozen=True)
class OcrFilteringResult:
    frame_count: int
    frames: list[FrameOcrFilterResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider: str = "unknown"

    def to_dict(self) -> dict:
        """JSON-serializable payload for Cloud jobs / downstream cleaners."""
        return {
            "provider": self.provider,
            "frame_count": self.frame_count,
            "warnings": list(self.warnings),
            "frames": [
                {
                    "frame_id": frame.frame_id,
                    "path": frame.path,
                    "time_ms": frame.time_ms,
                    "frame_width": frame.frame_width,
                    "frame_height": frame.frame_height,
                    "raw_box_count": frame.raw_box_count,
                    "filtered_out_count": frame.filtered_out_count,
                    "boxes": [
                        {
                            "x": box.x,
                            "y": box.y,
                            "width": box.width,
                            "height": box.height,
                            "text": box.text,
                            "confidence": box.confidence,
                            "vertices": [asdict(v) for v in box.vertices],
                        }
                        for box in frame.boxes
                    ],
                }
                for frame in self.frames
            ],
        }


def frame_id_from_path(path: Path) -> str:
    return path.stem
