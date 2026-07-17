"""
End-to-end hard-sub localization orchestrator (Phases 1 → 2 → 2.5 → 3+4).

Single entry: ``run_pipeline(video_path, output_path)``.
Delegates to ``media_pipeline.hardsub_e2e`` (shared with Final Review ANALYZE_OCR).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.media_pipeline.hardsub_e2e import HardsubE2EResult, run_hardsub_phases_1_to_4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """Artifact summary after a successful end-to-end run."""

    output_path: str
    sample_fps: int
    frame_count: int
    ocr_payload: dict[str, Any] = field(default_factory=dict)
    vi_texts: dict[str, str] = field(default_factory=dict)


def _configure_logging(verbose: bool = True) -> None:
    if logging.getLogger().handlers:
        return
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
    )


def _try_open_db_session() -> Session | None:
    """Best-effort DB for Caption AI settings; None keeps env/mock paths workable offline."""
    try:
        from src.db.session import get_session_factory

        return get_session_factory()()
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline_db_unavailable: %s (Caption AI falls back to env if needed)", exc)
        return None


def _to_pipeline_result(e2e: HardsubE2EResult) -> PipelineResult:
    return PipelineResult(
        output_path=e2e.output_path,
        sample_fps=e2e.sample_fps,
        frame_count=e2e.frame_count,
        ocr_payload=e2e.ocr_payload,
        vi_texts=e2e.vi_texts,
    )


def run_pipeline(
    video_path: str,
    output_path: str,
    *,
    sample_fps: int = 1,
    prefer_mock_ocr: bool = False,
    anti_seed: int | None = 42,
    db: Session | None = None,
    workspace_id: UUID | None = None,
    keep_temp: bool = False,
    ffmpeg_binary: str = "ffmpeg",
) -> PipelineResult:
    """
    Orchestrate Phases 1 → 2 → 2.5 → 3+4 (Single Render).

    1. Sample frames (1 or 2 fps) into a temp directory
    2. OCR + keep bottom-1/3 boxes (``OCR_ENDPOINT_URL`` / mock)
    3. Batch LLM translate → Vietnamese map (Ops Caption AI / env)
    4. One FFmpeg pass: mask + burn-in + anti-hash → ``output_path``

    Temp frames are always deleted in ``finally`` unless ``keep_temp=True``.
    """
    _configure_logging()
    owns_db = False
    session = db
    if session is None:
        session = _try_open_db_session()
        owns_db = session is not None

    try:
        e2e = run_hardsub_phases_1_to_4(
            video_path,
            output_path,
            sample_fps=sample_fps,
            prefer_mock_ocr=prefer_mock_ocr,
            anti_seed=anti_seed,
            db=session,
            workspace_id=workspace_id,
            keep_temp=keep_temp,
            ffmpeg_binary=ffmpeg_binary,
            render_progress=True,
        )
        return _to_pipeline_result(e2e)
    finally:
        if owns_db and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hard-sub E2E pipeline: sample → OCR → translate → single-pass render",
    )
    parser.add_argument(
        "--video",
        default="test_input.mp4",
        help="Input MP4 path (default: test_input.mp4 in cwd)",
    )
    parser.add_argument(
        "--out",
        default="test_output_hardsub.mp4",
        help="Output MP4 path",
    )
    parser.add_argument("--fps", type=int, choices=(1, 2), default=1, help="Sample fps (1 or 2)")
    parser.add_argument(
        "--mock-ocr",
        action="store_true",
        help="Use mock OCR (no Cloud Run) for dry runs",
    )
    parser.add_argument("--keep-temp", action="store_true", help="Do not delete temp frames")
    parser.add_argument("--seed", type=int, default=42, help="Anti-detection RNG seed")
    args = parser.parse_args(argv)

    _configure_logging()
    try:
        result = run_pipeline(
            args.video,
            args.out,
            sample_fps=args.fps,
            prefer_mock_ocr=args.mock_ocr,
            anti_seed=args.seed,
            keep_temp=args.keep_temp,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline FAILED: %s", exc)
        return 1

    if not result.output_path:
        logger.warning("OK but no output (no hard-sub boxes) frames=%s", result.frame_count)
        return 0

    logger.info("OK -> %s (frames=%s)", result.output_path, result.frame_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
