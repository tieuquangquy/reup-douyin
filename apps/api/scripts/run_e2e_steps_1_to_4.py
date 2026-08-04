"""Product E2E: continuous OCR authority → translate → single-pass clean+VI.

Replaces the sparse SKE→MagicVideoCleaner demo path. Authority is
``run_per_frame_position_authority`` (OCR_QUALITY_PROFILE=best) via
``run_hardsub_phases_1_to_4``; clean + Vietnamese burn use production
``render_video_single_pass`` (blur cover + Pillow VI).

Usage (from apps/api)::

    set PYTHONPATH=.
    set OCR_QUALITY_PROFILE=best
    set TRANSLATE_LLM_DRY=1
    set OCR_ENDPOINT_URL=http://127.0.0.1:8080/predict
    python scripts/run_e2e_steps_1_to_4.py [optional_video.mp4]

Outputs under ``E2E_OUT`` (default ``tmp_e2e_steps_1_4``):
  - final_complete.mp4
  - ocr_authority.json
  - vi_texts.json
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from src.media_pipeline.hardsub_e2e import run_hardsub_phases_1_to_4

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
OUT = Path(os.environ.get("E2E_OUT", str(API_ROOT / "tmp_e2e_steps_1_4")))
STORAGE = REPO_ROOT / "data" / "storage"
STAGING = REPO_ROOT / ".douyin_profiles" / "download_staging"


def _find_video(cli: Path | None) -> Path:
    if cli is not None and cli.is_file():
        return cli
    matches = list(STORAGE.rglob("*7657906958829468523*.mp4"))
    if matches:
        return matches[0]
    staged = STAGING / "7657906958829468523.mp4"
    if staged.is_file():
        return staged
    any_mp4 = list(STORAGE.rglob("*.mp4"))[:1]
    if any_mp4:
        return any_mp4[0]
    raise FileNotFoundError("No test video found (pass path as argv[1])")


def _safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _prepare_out(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Prefer wipe; on Windows a locked final_complete.mp4 must not block the run.
    for child in list(out_dir.iterdir()):
        try:
            if child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            _safe_print(f"[0] skip locked: {child.name}")
    return out_dir


def run_product_authority_e2e(
    *,
    video: Path | None = None,
    out_dir: Path | None = None,
    prefer_mock_ocr: bool = False,
) -> int:
    """
    Production authority path → ``final_complete.mp4``.

    Forces ``OCR_QUALITY_PROFILE=best`` for this process so Phase 2 uses
    dense per-frame position authority (not sparse SKE crop OCR).
    """
    os.environ["OCR_QUALITY_PROFILE"] = "best"
    dest_root = _prepare_out(Path(out_dir) if out_dir is not None else OUT)
    source = video if video is not None else _find_video(None)
    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")

    final_path = dest_root / "final_complete.mp4"
    # Write to a fresh name if previous final is locked in the editor.
    if final_path.exists():
        try:
            final_path.unlink()
        except OSError:
            final_path = dest_root / "final_complete_authority.mp4"

    _safe_print(f"[0] video={source}")
    _safe_print(f"[0] out={dest_root}")
    _safe_print(f"[0] profile=best dry={os.environ.get('TRANSLATE_LLM_DRY', '')}")

    t0 = time.perf_counter()
    result = run_hardsub_phases_1_to_4(
        source,
        final_path,
        prefer_mock_ocr=prefer_mock_ocr,
        force_refresh=True,
        keep_temp=False,
    )
    elapsed = time.perf_counter() - t0

    if not result.output_path:
        _safe_print("[FAIL] hardsub produced no output (no boxes?)")
        (dest_root / "ocr_authority.json").write_text(
            json.dumps(result.ocr_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1

    (dest_root / "ocr_authority.json").write_text(
        json.dumps(result.ocr_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (dest_root / "vi_texts.json").write_text(
        json.dumps(result.vi_texts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    meta = {
        "ocr_provider_name": result.ocr_provider_name,
        "caption_ai_source": result.caption_ai_source,
        "frame_count": result.frame_count,
        "sample_fps": result.sample_fps,
        "output_path": result.output_path,
        "elapsed_s": round(elapsed, 2),
    }
    (dest_root / "e2e_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _safe_print(
        f"[OK] COMPLETE_VIDEO={result.output_path} "
        f"provider={result.ocr_provider_name} elapsed_s={elapsed:.1f}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cli_video = Path(args[0]) if args else None
    video = _find_video(cli_video)
    return run_product_authority_e2e(video=video, out_dir=OUT)


if __name__ == "__main__":
    raise SystemExit(main())
