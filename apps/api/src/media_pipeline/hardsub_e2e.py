"""Shared hard-sub E2E core: Phase 1 → 2 → 2.5 → 3+4 (file out + payloads).

Used by CLI ``main_pipeline`` and Final Review ``OcrPipelineService``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.media_pipeline.frame_sampling.backend import extract_phase1_frames
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    MasterPhase1Extractor,
    ocr_timeline_keyframes,
    timeline_to_ocr_payload,
)
from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import build_default_ocr_provider
from src.media_pipeline.translator.service import translate_subtitles
from src.media_pipeline.video_renderer.renderer import (
    render_image_with_overlays,
    render_video_single_pass,
)

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
    render_progress: bool | Callable[[float | None, str], None] = True,
    ocr_cache_path: str | Path | None = None,
    force_refresh: bool = False,
    use_master_phase1: bool | None = None,
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
        from src.media_pipeline.ocr_filtering.ocr_quality_profile import is_best_ocr_profile

        use_master_phase1 = (
            bool(use_master_phase1)
            if use_master_phase1 is not None
            else is_best_ocr_profile()
        ) and not prefer_mock_ocr
        master_root = temp_root / "master_phase1"
        frame_paths: list[str] = []
        frame_time_ms: list[int] = []

        if use_master_phase1:
            logger.info(
                "Phase 1: MasterPhase1Extractor (SSOT timeline; no per-frame re-scan)"
            )
            master = MasterPhase1Extractor().extract(source, master_root)
            frame_count_master = int(master.frame_count)
            # Sparse keyframe paths for optional thumbnail attach only.
            frame_paths = [
                str(master.frames_dir / Path(str(e.get("best_keyframe_path") or "")).name)
                for e in master.timeline
                if (master.frames_dir / Path(str(e.get("best_keyframe_path") or "")).name).is_file()
            ]
            frame_time_ms = [
                int(round(int(e.get("start_frame") or 0) * 1000.0 / max(master.fps, 1e-6)))
                for e in master.timeline
            ]
            logger.info(
                "Phase 1 done: tracks=%s frames=%s timeline=%s",
                len(master.timeline),
                frame_count_master,
                master.timeline_path,
            )

            _progress("phase2_ocr", 25)
            logger.info("Phase 2: OCR keyframes from master timeline only...")
            timeline = ocr_timeline_keyframes(
                list(master.timeline),
                root_dir=master_root,
                prefer_mock=prefer_mock_ocr,
                video_path=source,
                frame_width=master.frame_width,
                frame_height=master.frame_height,
            )
            from src.media_pipeline.frame_sampling.ocr_translate_gate import (
                finalize_ocr_for_translate,
            )

            timeline, gate_audit = finalize_ocr_for_translate(
                timeline,
                qa_dir=master_root / "qa",
                frame_w=master.frame_width,
                frame_h=master.frame_height,
            )
            # Phase 1 geometry remains immutable. OCR/translate decisions cross the
            # artifact boundary through the versioned Phase 2 contract instead of
            # overwriting master_timeline.json.
            from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
                build_phase2_contract,
            )

            phase2_contract = build_phase2_contract(
                timeline,
                phase1_timeline_path=master.timeline_path,
                provider_mode="local",
                model_version=(
                    os.environ.get("LOCAL_OCR_MODEL_VERSION", "").strip()
                    or "ppocrv6-medium-det-rec"
                ),
                frame_width=master.frame_width,
                frame_height=master.frame_height,
            )
            phase2_timeline_path = master_root / "phase2_ocr_timeline.json"
            phase2_timeline_path.write_text(
                json.dumps(phase2_contract, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            ocr_payload = timeline_to_ocr_payload(
                timeline,
                fps=master.fps,
                frame_count=master.frame_count,
                frame_width=master.frame_width,
                frame_height=master.frame_height,
            )
            ocr_name = "master_phase1"
            ocr_frame_count = int(ocr_payload.get("frame_count") or 0)
            logger.info(
                "Phase 2 done: provider=%s frames=%s tracks=%s translate_ready=%s",
                ocr_name,
                ocr_frame_count,
                len(timeline),
                gate_audit.get("ready"),
            )
        else:
            logger.info("Phase 1: Frame sampling (backend via OCR_FRAME_BACKEND)...")
            extracted = extract_phase1_frames(
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
            ske_summary = frames_dir / "summary.json"
            use_ske_crop_ocr = (
                ske_summary.is_file()
                and not prefer_mock_ocr
            )

            if use_ske_crop_ocr:
                from src.media_pipeline.ocr_filtering.analyze_ocr import (
                    CloudOCRAnalyzer,
                    load_crop_items_from_ske_dir,
                    ske_grouped_to_ocr_payload,
                )

                try:
                    crops = load_crop_items_from_ske_dir(frames_dir)
                    analyzer = CloudOCRAnalyzer()
                    grouped = analyzer.analyze_sync(crops)
                    ocr_payload = ske_grouped_to_ocr_payload(
                        grouped,
                        ske_dir=frames_dir,
                        provider="ske_cloud_ocr",
                    )
                    if not _ocr_payload_has_boxes(ocr_payload):
                        raise RuntimeError("SKE crop OCR produced no boxes")
                    ocr_name = "ske_cloud_ocr"
                    ocr_frame_count = int(ocr_payload.get("frame_count") or 0)
                    logger.info(
                        "Phase 2 ske_crop_ocr crops=%s hits=%s frames=%s",
                        len(crops),
                        sum(len(v) for v in grouped.values()),
                        ocr_frame_count,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ske_crop_ocr_failed fallback=run_ocr_filtering err=%s",
                        exc,
                    )
                    ocr_provider = build_default_ocr_provider(prefer_mock=prefer_mock_ocr)
                    ocr_kwargs: dict[str, Any] = {
                        "ocr_provider": ocr_provider,
                        "frame_time_ms": frame_time_ms,
                    }
                    if band_ratio is not None:
                        ocr_kwargs["band_ratio"] = float(band_ratio)
                    ocr_result = run_ocr_filtering(
                        frame_paths,
                        on_progress=_progress,
                        **ocr_kwargs,
                    )
                    ocr_payload = ocr_result.to_dict()
                    ocr_name = str(
                        getattr(ocr_provider, "provider_name", ocr_result.provider)
                        or "unknown"
                    )
                    ocr_frame_count = int(ocr_result.frame_count)
            else:
                ocr_provider = build_default_ocr_provider(prefer_mock=prefer_mock_ocr)
                ocr_kwargs = {
                    "ocr_provider": ocr_provider,
                    "frame_time_ms": frame_time_ms,
                }
                if band_ratio is not None:
                    ocr_kwargs["band_ratio"] = float(band_ratio)
                ocr_result = run_ocr_filtering(
                    frame_paths,
                    on_progress=_progress,
                    **ocr_kwargs,
                )
                ocr_payload = ocr_result.to_dict()
                ocr_name = str(
                    getattr(ocr_provider, "provider_name", ocr_result.provider)
                    or "unknown"
                )
                ocr_frame_count = int(ocr_result.frame_count)
            logger.info(
                "Phase 2 done: provider=%s frames=%s",
                ocr_name,
                ocr_frame_count,
            )

        # NOTE: run_per_frame_position_authority is intentionally unwired.
        # Master Phase 1 timeline is the geometry SSOT for the best profile.

        if not _ocr_payload_has_boxes(ocr_payload):
            logger.info("Phase 2: no boxes — skip translate/render")
            _progress("phases_complete", 95)
            return HardsubE2EResult(
                output_path="",
                sample_fps=fps,
                frame_count=int(ocr_frame_count or len(frame_paths)),
                ocr_payload=ocr_payload,
                vi_texts={},
                ocr_provider_name=ocr_name,
                caption_ai_source="skipped",
            )

        _progress("phase25_translate", 55)
        logger.info("Phase 2.5: Caption AI translate...")
        dry = os.environ.get("TRANSLATE_LLM_DRY", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        translate_artifact_dir = (
            (master_root / "qa") if use_master_phase1 else (temp_root / "qa")
        )
        if dry:
            caption_source = "dry"
            vi_texts = translate_subtitles(
                ocr_payload,
                artifact_dir=translate_artifact_dir,
            )
        else:
            from src.media_pipeline.translator.resolve import resolve_translator_settings

            settings = resolve_translator_settings(db=db, workspace_id=workspace_id)
            caption_source = settings.source
            vi_texts = translate_subtitles(
                ocr_payload,
                db=db,
                workspace_id=workspace_id,
                settings=settings,
                artifact_dir=translate_artifact_dir,
            )
        logger.info("Phase 2.5 done: %s segments source=%s", len(vi_texts), caption_source)

        _progress("phase34_render", 75)
        logger.info("Phase 3+4: Single Render...")
        destination.parent.mkdir(parents=True, exist_ok=True)

        from src.media_pipeline.video_renderer.render_finalize import (
            finalize_overlays_for_render,
        )
        from src.media_pipeline.video_renderer.renderer import probe_video_duration_ms

        try:
            duration_ms = probe_video_duration_ms(source, ffmpeg_binary=ffmpeg_binary)
        except Exception:  # noqa: BLE001 — duration probe is best-effort for overlays
            duration_ms = None
        overlays, overlay_stats = finalize_overlays_for_render(
            ocr_payload,
            vi_texts,
            hold_ms=500,
            video_duration_ms=duration_ms,
            artifact_dir=translate_artifact_dir,
        )
        logger.info(
            "Phase 3 pre-render: segments=%s source=%s vi_dropped=%s",
            overlay_stats.get("segments"),
            overlay_stats.get("source"),
            overlay_stats.get("vi_dropped"),
        )

        attached_pic: Path | None = None
        thumb_src = next((p for p in frame_paths if Path(p).name == "thumbnail.jpg"), None)
        if thumb_src is not None and Path(thumb_src).is_file():
            try:
                thumb_overlays = [seg for seg in overlays if int(seg.start_ms) == 0]
                covered = temp_root / "thumbnail_covered.jpg"
                render_image_with_overlays(
                    thumb_src,
                    covered,
                    thumb_overlays,
                    anti_seed=anti_seed,
                    ffmpeg_binary=ffmpeg_binary,
                )
                if covered.is_file():
                    attached_pic = covered
            except Exception as exc:  # noqa: BLE001 — cover attach is best-effort
                logger.warning("thumbnail_cover_failed error=%s", str(exc)[:200])

        rendered = render_video_single_pass(
            source,
            destination,
            overlays=overlays,
            anti_seed=anti_seed,
            ffmpeg_binary=ffmpeg_binary,
            progress=render_progress,
            attached_pic=attached_pic,
            sample_dir=Path(translate_artifact_dir) / "render_samples",
        )
        logger.info("Phase 3+4 done: %s", rendered)
        _progress("phases_complete", 95)

        # Persist Master Phase 1 SSOT beside the final video (temp is deleted).
        if use_master_phase1 and master_root.is_dir():
            try:
                side = destination.parent
                src_timeline = master_root / "master_timeline.json"
                if src_timeline.is_file():
                    shutil.copy2(src_timeline, side / "master_timeline.json")
                src_phase2_timeline = master_root / "phase2_ocr_timeline.json"
                if src_phase2_timeline.is_file():
                    shutil.copy2(
                        src_phase2_timeline,
                        side / "phase2_ocr_timeline.json",
                    )
                src_frames = master_root / "frames"
                if src_frames.is_dir():
                    dest_frames = side / "master_frames"
                    if dest_frames.exists():
                        shutil.rmtree(dest_frames, ignore_errors=True)
                    shutil.copytree(src_frames, dest_frames)
                # Phase 2.5 fossils for audit / re-render without re-calling LLM.
                qa_dir = master_root / "qa"
                for name in (
                    "translate_unique.json",
                    "vi_texts.json",
                    "translate_stats.json",
                    "translate_queue.json",
                    "overlays.json",
                    "overlay_stats.json",
                ):
                    src_fossil = qa_dir / name
                    if src_fossil.is_file():
                        shutil.copy2(src_fossil, side / name)
                src_samples = qa_dir / "render_samples"
                if src_samples.is_dir():
                    dest_samples = side / "render_samples"
                    if dest_samples.exists():
                        shutil.rmtree(dest_samples, ignore_errors=True)
                    shutil.copytree(src_samples, dest_samples)
            except OSError as exc:
                logger.warning("master_phase1_persist_failed err=%s", exc)

        return HardsubE2EResult(
            output_path=str(Path(rendered).resolve()),
            sample_fps=fps,
            frame_count=int(ocr_frame_count or len(frame_paths)),
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
