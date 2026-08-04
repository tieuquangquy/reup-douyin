"""Runtime TTS provenance extracted from render-prep artifacts.

Recipe configuration is an intent.  A render-prep manifest is evidence of what
actually synthesized the audio.  This module keeps that distinction explicit and
provides one verifier shared by E2E reporting, recipe candidates, and recipe locks.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TTS_PROVENANCE_SCHEMA_VERSION = "tts_runtime_provenance_v1"
TTS_PROVENANCE_AUTHORITY = "e2e_render_prep_manifests_v1"
TTS_PROVENANCE_VERIFIED = "VERIFIED_SINGLE_RUNTIME_CONFIG"


class PipelineTtsProvenanceError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineTtsProvenanceError(
            f"Cannot read valid TTS provenance artifact {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise PipelineTtsProvenanceError(
            f"TTS provenance artifact {path.name} must contain an object"
        )
    return payload


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_rate(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _runtime_config(
    *,
    provider: Any,
    model_id: Any,
    voice_id: Any,
    language_code: Any,
    speaking_rate: Any,
) -> dict[str, Any]:
    return {
        "provider": _clean_text(provider).lower(),
        "model_id": _clean_text(model_id),
        "voice_id": _clean_text(voice_id),
        "language_code": _clean_text(language_code),
        "speaking_rate": _clean_rate(speaking_rate),
    }


def _config_is_complete(config: dict[str, Any]) -> bool:
    return bool(
        config.get("provider")
        and config.get("voice_id")
        and float(config.get("speaking_rate") or 0.0) > 0.0
    )


def extract_case_tts_provenance(
    *,
    case_root: str | Path,
    run_root: str | Path,
    audio_strategy: str,
) -> dict[str, Any]:
    """Extract one case's effective TTS configuration from its render manifest."""

    root = Path(case_root).resolve()
    run = Path(run_root).resolve()
    manifest_path = (root / "render_prep_manifest.json").resolve()
    narration_expected = "vietnamese_narration" in _clean_text(audio_strategy).lower()
    base: dict[str, Any] = {
        "schema_version": TTS_PROVENANCE_SCHEMA_VERSION,
        "audio_strategy": _clean_text(audio_strategy),
    }
    if not manifest_path.is_file():
        if narration_expected:
            return {
                **base,
                "status": "INVALID",
                "reason": "TTS_MANIFEST_MISSING_FOR_NARRATION",
            }
        return {
            **base,
            "status": "NOT_APPLICABLE",
            "reason": "RENDER_STRATEGY_HAS_NO_VIETNAMESE_NARRATION",
        }
    if not manifest_path.is_relative_to(run):
        return {
            **base,
            "status": "INVALID",
            "reason": "TTS_MANIFEST_OUTSIDE_RUN_ROOT",
        }

    try:
        manifest = _load_object(manifest_path)
    except PipelineTtsProvenanceError:
        return {
            **base,
            "status": "INVALID",
            "reason": "TTS_MANIFEST_INVALID_JSON",
        }
    clips = list(dict(manifest.get("current_outputs") or {}).get("tts_clips") or [])
    if not clips:
        return {
            **base,
            "status": "INVALID" if narration_expected else "NOT_APPLICABLE",
            "reason": (
                "TTS_CLIPS_MISSING_FOR_NARRATION"
                if narration_expected
                else "TTS_MANIFEST_HAS_NO_CLIPS"
            ),
            "manifest": {
                "path": manifest_path.relative_to(run).as_posix(),
                "file_sha256": _sha256_file(manifest_path),
            },
        }

    summary = dict(manifest.get("provider_summary") or {})
    summary_voice = dict(summary.get("voice_config") or {})
    summary_config = _runtime_config(
        provider=summary.get("tts_provider"),
        model_id=summary.get("model_id"),
        voice_id=summary_voice.get("voice_id"),
        language_code=summary_voice.get("language_code"),
        speaking_rate=summary_voice.get("speaking_rate"),
    )
    clip_configs: list[dict[str, Any]] = []
    for row in clips:
        metadata = dict(dict(row or {}).get("metadata") or {})
        provider_meta = dict(metadata.get("provider") or {})
        clip_configs.append(
            _runtime_config(
                provider=provider_meta.get("provider") or summary_config["provider"],
                model_id=provider_meta.get("model_id") or summary_config["model_id"],
                voice_id=provider_meta.get("voice_id") or summary_config["voice_id"],
                language_code=(
                    provider_meta.get("language")
                    or provider_meta.get("language_code")
                    or summary_config["language_code"]
                ),
                speaking_rate=(
                    provider_meta.get("speaking_rate")
                    if provider_meta.get("speaking_rate") is not None
                    else summary_config["speaking_rate"]
                ),
            )
        )
    first = clip_configs[0]
    if not _config_is_complete(first) or any(row != first for row in clip_configs[1:]):
        return {
            **base,
            "status": "INVALID",
            "reason": "TTS_CLIP_RUNTIME_CONFIG_MISSING_OR_MIXED",
            "clip_count": len(clips),
            "manifest": {
                "path": manifest_path.relative_to(run).as_posix(),
                "file_sha256": _sha256_file(manifest_path),
            },
        }
    for key in ("provider", "voice_id", "language_code", "speaking_rate"):
        summary_value = summary_config.get(key)
        if summary_value not in ("", 0.0) and summary_value != first.get(key):
            return {
                **base,
                "status": "INVALID",
                "reason": "TTS_PROVIDER_SUMMARY_CLIP_MISMATCH",
                "clip_count": len(clips),
                "manifest": {
                    "path": manifest_path.relative_to(run).as_posix(),
                    "file_sha256": _sha256_file(manifest_path),
                },
            }

    config_sha256 = _sha256_json(first)
    return {
        **base,
        "status": "VERIFIED",
        **first,
        "runtime_config_sha256": config_sha256,
        "clip_count": len(clips),
        "manifest": {
            "path": manifest_path.relative_to(run).as_posix(),
            "file_sha256": _sha256_file(manifest_path),
        },
    }


def aggregate_tts_provenance(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(dict(case).get("tts") or {}) for case in cases]
    invalid = [row for row in rows if row.get("status") == "INVALID"]
    verified = [row for row in rows if row.get("status") == "VERIFIED"]
    not_applicable = [row for row in rows if row.get("status") == "NOT_APPLICABLE"]
    base = {
        "schema_version": TTS_PROVENANCE_SCHEMA_VERSION,
        "authority": TTS_PROVENANCE_AUTHORITY,
        "tts_case_count": len(verified),
        "not_applicable_case_count": len(not_applicable),
        "invalid_case_count": len(invalid),
    }
    if invalid:
        return {**base, "status": "INVALID_CASE_EVIDENCE"}
    if not verified:
        return {**base, "status": "NO_TTS_RUNTIME_EVIDENCE"}
    configs = {
        str(row.get("runtime_config_sha256") or ""): _runtime_config(
            provider=row.get("provider"),
            model_id=row.get("model_id"),
            voice_id=row.get("voice_id"),
            language_code=row.get("language_code"),
            speaking_rate=row.get("speaking_rate"),
        )
        for row in verified
    }
    if "" in configs or len(configs) != 1:
        return {
            **base,
            "status": "RUNTIME_CONFIG_MISMATCH",
            "runtime_config_count": len(configs),
        }
    config_sha256, config = next(iter(configs.items()))
    return {
        **base,
        "status": TTS_PROVENANCE_VERIFIED,
        **config,
        "runtime_config_sha256": config_sha256,
        "manifest_count": len(verified),
    }


def verify_e2e_tts_provenance(
    *,
    e2e_report: dict[str, Any],
    e2e_report_path: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    """Re-read every referenced manifest before promoting TTS evidence."""

    report_path = Path(e2e_report_path).resolve()
    run = report_path.parent
    workspace = Path(workspace_root).resolve()
    claimed = dict(e2e_report.get("tts_provenance") or {})
    if claimed.get("status") != TTS_PROVENANCE_VERIFIED:
        raise PipelineTtsProvenanceError(
            "E2E report does not contain verified single-config TTS provenance"
        )
    rebuilt_cases: list[dict[str, Any]] = []
    for case in list(e2e_report.get("cases") or []):
        case = dict(case or {})
        recorded = dict(case.get("tts") or {})
        if recorded.get("status") == "NOT_APPLICABLE":
            case_root = (run / _clean_text(case.get("case_id"))).resolve()
            if not case_root.is_relative_to(run) or not case_root.is_dir():
                raise PipelineTtsProvenanceError(
                    f"TTS case root is missing for case {case.get('case_id')}"
                )
            rebuilt = extract_case_tts_provenance(
                case_root=case_root,
                run_root=run,
                audio_strategy=str(
                    dict(case.get("render") or {}).get("audio_strategy") or ""
                ),
            )
            if rebuilt != recorded:
                raise PipelineTtsProvenanceError(
                    f"No-TTS evidence drifted for case {case.get('case_id')}"
                )
            rebuilt_cases.append({"tts": rebuilt})
            continue
        manifest_ref = dict(recorded.get("manifest") or {})
        manifest_path = (run / _clean_text(manifest_ref.get("path"))).resolve()
        if (
            not manifest_path.is_relative_to(workspace)
            or not manifest_path.is_relative_to(run)
            or not manifest_path.is_file()
            or _sha256_file(manifest_path)
            != _clean_text(manifest_ref.get("file_sha256")).lower()
        ):
            raise PipelineTtsProvenanceError(
                f"TTS manifest evidence is missing or stale for case {case.get('case_id')}"
            )
        rebuilt = extract_case_tts_provenance(
            case_root=manifest_path.parent,
            run_root=run,
            audio_strategy=str(dict(case.get("render") or {}).get("audio_strategy") or ""),
        )
        comparable_keys = (
            "status",
            "provider",
            "model_id",
            "voice_id",
            "language_code",
            "speaking_rate",
            "runtime_config_sha256",
            "clip_count",
            "manifest",
        )
        if any(rebuilt.get(key) != recorded.get(key) for key in comparable_keys):
            raise PipelineTtsProvenanceError(
                f"TTS manifest evidence drifted for case {case.get('case_id')}"
            )
        rebuilt_cases.append({"tts": rebuilt})
    rebuilt_aggregate = aggregate_tts_provenance(rebuilt_cases)
    if rebuilt_aggregate != claimed:
        raise PipelineTtsProvenanceError(
            "E2E aggregate TTS provenance does not match its manifest evidence"
        )
    return {
        "provider": claimed["provider"],
        "model_id": claimed.get("model_id", ""),
        "voice_id": claimed["voice_id"],
        "language_code": claimed.get("language_code", ""),
        "speaking_rate": claimed["speaking_rate"],
        "authority": TTS_PROVENANCE_AUTHORITY,
        "runtime_config_sha256": claimed["runtime_config_sha256"],
        "verified_case_count": int(claimed.get("tts_case_count") or 0),
    }
