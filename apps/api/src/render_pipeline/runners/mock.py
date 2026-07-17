from __future__ import annotations

from pathlib import Path

from src.render_pipeline.types import ExportInput, ExportResult


class CopyMockRenderRunner:
    runner_name = "copy_mock"

    def export(self, export_input: ExportInput) -> ExportResult:
        Path(export_input.output_path).parent.mkdir(parents=True, exist_ok=True)
        source = Path(export_input.source_video_path)
        content = source.read_bytes() if source.exists() else b"mock-render"
        Path(export_input.output_path).write_bytes(content + b"\nrendered-with-vietnamese-audio-and-subtitles")
        return ExportResult(
            output_path=export_input.output_path,
            log_text="mock render completed",
            warnings=["mock_export_runner"],
            command=["mock-render"],
        )
