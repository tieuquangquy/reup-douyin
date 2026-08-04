"""Materialize a DB render-prep manifest as a Phase-4 V2 handoff artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from src.db.session import get_session_factory
from src.models.ingestion import SourceVideo
from src.tts_pipeline.services.tts_service import TtsPipelineService


def materialize(case_root: str | Path, source_video_id: str) -> dict:
    root = Path(case_root).resolve()
    with get_session_factory()() as db:
        manifest = TtsPipelineService(db).get_render_prep_manifest(UUID(source_video_id))
        source_video = db.get(SourceVideo, UUID(source_video_id))
        if source_video is None:
            raise RuntimeError("Source video is missing")
        source_duration = float(source_video.duration_seconds or 0.0)
        if source_duration <= 0:
            raise RuntimeError("Source video duration authority is missing")
    outputs = dict(manifest.get("current_outputs") or {})
    joined_by_key = {
        str(row.get("storage_key") or ""): dict(row)
        for row in list(outputs.get("joined_narration") or [])
        if isinstance(row, dict) and str(row.get("storage_key") or "")
    }
    joined = list(joined_by_key.values())
    if len(joined) != 1:
        raise RuntimeError("Exactly one joined narration asset is required")
    upgraded = json.loads(json.dumps(manifest, ensure_ascii=False, default=str))
    upgraded["manifest_version"] = "RENDER_PREP_MANIFEST_V2"
    upgraded["pipeline_version"] = str(upgraded.get("pipeline_version") or "TTS_PIPELINE_V1")
    upgraded["source_video"] = {
        **dict(upgraded.get("source_video") or {}),
        "id": str(source_video_id),
        "duration_seconds": source_duration,
    }
    upgraded["current_outputs"]["joined_narration"] = joined
    narration_path = Path(str(joined[0].get("metadata_json", {}).get("absolute_path") or ""))
    if not narration_path.is_file():
        raise RuntimeError("Joined narration file is missing")
    digest = hashlib.sha256(narration_path.read_bytes()).hexdigest()
    upgraded["current_outputs"]["joined_narration"][0].update(
        {"sha256": digest, "size_bytes": narration_path.stat().st_size}
    )
    upgraded["render_contract"] = {
        **dict(upgraded.get("render_contract") or {}),
        "audio_strategy": "mix_vietnamese_narration_with_background_stem",
    }
    path = root / "render_prep_manifest.json"
    path.write_text(json.dumps(upgraded, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "RENDER_PREP_MANIFEST_V2_MATERIALIZED", "path": path.name, "joined_narration": joined[0]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("case_root")
    parser.add_argument("source_video_id")
    args = parser.parse_args()
    print(json.dumps(materialize(args.case_root, args.source_video_id), ensure_ascii=False))
