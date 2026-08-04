"""Refresh the reproducible Phase 4 recipe after a late audio rebind."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.media_pipeline.video_renderer.phase4_input_contract import _resolve_phase1_source_path
from src.media_pipeline.video_renderer.render_authority import (
    build_reproducible_render_recipe,
    resolve_audio_authority,
)
from src.media_pipeline.video_renderer.visual_remediation import apply_visual_remediation
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from scripts.run_phase4_preflight import _runtime_versions


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def refresh(case_root: str | Path) -> dict[str, Any]:
    root = Path(case_root).resolve()
    input_path = root / "phase4_render_input.json"
    contract = _load(input_path)
    effective, _ = apply_visual_remediation(root, contract, contract_path=input_path)
    manifest_path = root / "render_prep_manifest.json"
    manifest = _load(manifest_path)
    audio = resolve_audio_authority(manifest, allow_source_passthrough=False)
    if str(audio.get("status") or "") != "READY":
        raise ValueError("Audio authority is not ready")
    source_meta = _load(root / "phase1_meta.json")
    source = _resolve_phase1_source_path(root, str(source_meta.get("video") or ""))
    source_ref = dict(dict(effective.get("refs") or {}).get("source_video_ref") or {})
    font = resolve_drawtext_font()
    settings = get_settings()
    recipe = build_reproducible_render_recipe(
        phase4_input_sha256=_sha256_file(input_path),
        source_video_sha256=str(source_ref.get("sha256") or _sha256_file(source)),
        font_sha256=_sha256_file(font),
        policy_version=str(effective.get("render_policy_version") or "unknown"),
        runtime_versions=_runtime_versions(),
        audio_authority=audio,
        color_authority=dict(effective.get("authorities") or {}).get("color") or {},
        timebase_authority=dict(effective.get("authorities") or {}).get("timebase") or {},
        anti_transform_enabled=False,
        anti_seed=None,
        encoding_policy={
            "requested_encoder": str(settings.render_video_encoder or "auto"),
            "hardware_smoke_probe": bool(settings.render_hardware_encoder_smoke_probe),
            "hardware_fallback_enabled": bool(settings.render_hardware_encoder_fallback_enabled),
            "geometry_transform": "none",
            "color_transform": "none",
            "invisible_perturbation": False,
        },
    )
    target = root / "phase4_render_recipe.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return {
        "status": "RECIPE_REFRESHED",
        "path": target.name,
        "sha256": _sha256_file(target),
        "phase4_input_sha256": _sha256_file(input_path),
        "audio_strategy": audio.get("strategy"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.refresh_phase4_render_recipe")
    parser.add_argument("case_root")
    args = parser.parse_args()
    try:
        print(json.dumps(refresh(args.case_root), ensure_ascii=False))
    except (OSError, ValueError, KeyError) as exc:
        print(f"[P4-RECIPE][FAIL] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
