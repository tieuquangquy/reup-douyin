"""Declarative plan for the Reup auto pipeline.

The orchestrator asks this module a single question — "what runs next?" — instead of
each completion handler deciding for itself. Two inputs shape the answer: the stop
point implied by the pipeline mode, and whether the clip needs dubbing at all.
"""

from __future__ import annotations

from src.services.reup_pipeline_meta import (
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_MODE_AUTO_TO_TTS,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_DOWNLOAD,
    PIPELINE_STEP_OCR,
    PIPELINE_STEP_RENDER,
    PIPELINE_STEP_TRANSLATE,
    PIPELINE_STEP_TTS,
)

PIPELINE_STEP_ORDER: tuple[str, ...] = (
    PIPELINE_STEP_DOWNLOAD,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_TRANSLATE,
    PIPELINE_STEP_TTS,
    PIPELINE_STEP_OCR,
    PIPELINE_STEP_RENDER,
)

# Only the voice steps depend on spoken dialogue. Hardsub cleanup and render apply to a
# silent clip too, because burned-in Chinese text is independent of the audio track.
DUBBING_STEPS = frozenset({PIPELINE_STEP_TRANSLATE, PIPELINE_STEP_TTS})

_AUTO_LAST_STEP: dict[str, str] = {
    PIPELINE_MODE_AUTO_TO_TTS: PIPELINE_STEP_TTS,
    PIPELINE_MODE_AUTO_TO_RENDER: PIPELINE_STEP_RENDER,
}


def auto_last_step(mode: str) -> str | None:
    """Last step an auto item may run on its own, or None for manual items."""
    return _AUTO_LAST_STEP.get(mode)


def next_pipeline_step(*, current_step: str | None, mode: str, skip_dubbing: bool) -> str | None:
    """Step to enqueue after ``current_step`` finished, or None when the plan is done."""
    last_step = auto_last_step(mode)
    if last_step is None:
        return None

    limit = PIPELINE_STEP_ORDER.index(last_step)
    if current_step is None:
        start = 0
    elif current_step in PIPELINE_STEP_ORDER:
        start = PIPELINE_STEP_ORDER.index(current_step) + 1
    else:
        return None

    for index in range(start, limit + 1):
        step = PIPELINE_STEP_ORDER[index]
        if skip_dubbing and step in DUBBING_STEPS:
            continue
        return step
    return None
