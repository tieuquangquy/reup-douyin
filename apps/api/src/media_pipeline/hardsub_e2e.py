"""Shared hard-sub E2E core: Phase 1 → 2 → 2.5 → 3+4 (file out + payloads).

Used by CLI ``main_pipeline`` and Final Review ``OcrPipelineService``.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames_detailed
from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import build_default_ocr_provider
from src.media_pipeline.translator.service import translate_subtitles
from src.media_pipeline.video_renderer.renderer import render_video_single_pass

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int | None], None]

CLEAN_METHOD_SINGLE_PASS = "single_pass_mask_vi_antihash"
PIPELINE_BACKEND = "media_e2e_v1"


def _ocr_payload_has_boxes(payload: dict[str, Any]) -> bool:
    for frame in payload.get("frames") or []:
        if isinstance(frame, dict) and frame.get("boxes"):
            return True
    return False


@dataclass(frozen=True)
class HardsubE2EResult:
    """Artifacts from a completed Phase 1–4 run (before asset persistence)."""

    output_path: str
    sample_fps: int
    frame_count: int
    ocr_payload: dict[str, Any] = field(default_factory=dict)
    vi_texts: dict[str, str] = field(default_factory=dict)
    ocr_provider_name: str = "unknown"
    caption_ai_source: str = "unknown"


def normalize_pipeline_sample_fps(sample_fps: float | int) -> int:
    """STRICT 1|2 for frame sampling; Final Review default 1.0 → 1."""
    value = float(sample_fps)
    if value in (2.0, 2):
        return 2
    return 1


def run_hardsub_phases_1_to_4(
    video_path: str | Path,
    output_path: str | Path,
    *,
    sample_fps: float | int = 1,
    prefer_mock_ocr: bool = False,
    anti_seed: int | None = 42,
    db: Session | None = None,
    workspace_id: UUID | None = None,
    keep_temp: bool = False,
    ffmpeg_binary: str = "ffmpeg",
    band_ratio: float | None = None,
    on_progress: ProgressCallback | None = None,
    render_progress: bool = True,
) -> HardsubE2EResult:
    """
    Run Phase 1–4 into ``output_path``. Always deletes temp frames unless ``keep_temp``.
    """
    source = Path(video_path)
    destination = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(f"Input video not found: {source}")

    fps = normalize_pipeline_sample_fps(sample_fps)
    temp_root = Path(tempfile.mkdtemp(prefix="reup_hardsub_pipeline_"))
    frames_dir = temp_root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    def _progress(phase: str, percent: int | None) -> None:
        if on_progress is not None:
            on_progress(phase, percent)

    logger.info("hardsub_e2e_start video=%s output=%s temp=%s", source, destination, temp_root)
    caption_source = "unknown"
    try:
        _progress("phase1_sample", 5)
        logger.info("Phase 1: Frame sampling (%s fps)...", fps)
        extracted = extract_video_frames_detailed(
            source,
            frames_dir,
            sample_fps=fps,
            ffmpeg_binary=ffmpeg_binary,
        )
        frame_paths = [frame.path for frame in extracted]
        frame_time_ms = [int(frame.time_ms) for frame in extracted]
        if not frame_paths:
            raise RuntimeError("Phase 1 produced no frames")
        logger.info("Phase 1 done: %s frames", len(frame_paths))

        _progress("phase2_ocr", 25)
        logger.info("Phase 2: OCR filtering...")
        ocr_provider = build_default_ocr_provider(prefer_mock=prefer_mock_ocr)
        ocr_kwargs: dict[str, Any] = {
            "ocr_provider": ocr_provider,
            "frame_time_ms": frame_time_ms,
        }
        if band_ratio is not None:
            ocr_kwargs["band_ratio"] = float(band_ratio)
        ocr_result = run_ocr_filtering(frame_paths, **ocr_kwargs)
        ocr_payload = ocr_result.to_dict()
        ocr_name = str(getattr(ocr_provider, "provider_name", ocr_result.provider) or "unknown")
        logger.info("Phase 2 done: provider=%s frames=%s", ocr_name, ocr_result.frame_count)

        if not _ocr_payload_has_boxes(ocr_payload):
            logger.info("Phase 2: no boxes — skip translate/render")
            _progress("phases_complete", 95)
            return HardsubE2EResult(
                output_path="",
                sample_fps=fps,
                frame_count=len(frame_paths),
                ocr_payload=ocr_payload,
                vi_texts={},
                ocr_provider_name=ocr_name,
                caption_ai_source="skipped",
            )

        _progress("phase25_translate", 55)
        logger.info("Phase 2.5: Caption AI translate...")
        from src.media_pipeline.translator.resolve import resolve_translator_settings

        settings = resolve_translator_settings(db=db, workspace_id=workspace_id)
        caption_source = settings.source
        vi_texts = translate_subtitles(
            ocr_payload,
            db=db,
            workspace_id=workspace_id,
            settings=settings,
        )
        logger.info("Phase 2.5 done: %s segments source=%s", len(vi_texts), caption_source)

        _progress("phase34_render", 75)
        logger.info("Phase 3+4: Single Render...")
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_video_single_pass(
            source,
            destination,
            ocr_payload=ocr_payload,
            vi_texts=vi_texts,
            anti_seed=anti_seed,
            ffmpeg_binary=ffmpeg_binary,
            progress=render_progress,
        )
        logger.info("Phase 3+4 done: %s", rendered)
        _progress("phases_complete", 95)

        return HardsubE2EResult(
            output_path=str(Path(rendered).resolve()),
            sample_fps=fps,
            frame_count=len(frame_paths),
            ocr_payload=ocr_payload,
            vi_texts=dict(vi_texts),
            ocr_provider_name=ocr_name,
            caption_ai_source=caption_source,
        )
    finally:
        if keep_temp:
            logger.warning("keep_temp=True — frames left at %s", temp_root)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)
            logger.info("Temp cleaned: %s", temp_root)
