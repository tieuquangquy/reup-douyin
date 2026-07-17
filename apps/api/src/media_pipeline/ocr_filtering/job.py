"""Serverless-friendly job wrapper for Phase 2 OCR filtering."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import build_default_ocr_provider
from src.media_pipeline.ocr_filtering.subtitle_band import BOTTOM_BAND_RATIO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrFilteringJobRequest:
    frame_paths: list[str]
    frame_time_ms: list[int] = field(default_factory=list)
    band_ratio: float = BOTTOM_BAND_RATIO
    prefer_mock_ocr: bool = False
    output_json_path: str | None = None


@dataclass(frozen=True)
class OcrFilteringJobResult:
    frame_count: int
    provider: str
    payload: dict
    output_json_path: str | None = None


def run_ocr_filtering_job(request: OcrFilteringJobRequest) -> OcrFilteringJobResult:
    """Execute OCR + bottom-band filter; optionally write JSON artifact."""
    provider = build_default_ocr_provider(prefer_mock=request.prefer_mock_ocr)
    result = run_ocr_filtering(
        [Path(p) for p in request.frame_paths],
        ocr_provider=provider,
        frame_time_ms=request.frame_time_ms or None,
        band_ratio=request.band_ratio,
    )
    payload = result.to_dict()
    output_path = request.output_json_path
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("ocr_filtering_json_written", extra={"path": str(path)})
    return OcrFilteringJobResult(
        frame_count=result.frame_count,
        provider=result.provider,
        payload=payload,
        output_json_path=output_path,
    )
