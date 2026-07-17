"""Types for Phase 1 frame sampling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# STRICT CONSTRAINT: only 1 fps or 2 fps — never full-video dump / other rates.
SampleFps = Literal[1, 2]

ALLOWED_SAMPLE_FPS: frozenset[int] = frozenset({1, 2})
DEFAULT_SAMPLE_FPS: SampleFps = 1


@dataclass(frozen=True)
class ExtractedFrame:
    """One successfully extracted still frame."""

    path: Path
    frame_index: int
    time_ms: int
