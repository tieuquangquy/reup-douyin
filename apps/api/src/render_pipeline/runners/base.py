from __future__ import annotations

from typing import Protocol

from src.render_pipeline.types import ExportInput, ExportResult


class ExportRunner(Protocol):
    runner_name: str

    def export(self, export_input: ExportInput) -> ExportResult:
        ...
