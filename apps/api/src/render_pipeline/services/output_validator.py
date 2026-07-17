from __future__ import annotations

from pathlib import Path

from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.types import VideoProbe


def validate_render_output(output_path: str, output_probe: VideoProbe, source_probe: VideoProbe) -> None:
    path = Path(output_path)
    if not path.exists():
        raise RenderPipelineError(RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED, "Rendered output file does not exist")
    if path.stat().st_size <= 0:
        raise RenderPipelineError(RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED, "Rendered output file is empty")
    if source_probe.duration_seconds and output_probe.duration_seconds:
        ratio = output_probe.duration_seconds / source_probe.duration_seconds
        if ratio < 0.5 or ratio > 1.8:
            raise RenderPipelineError(RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED, "Rendered duration differs too much from source")
