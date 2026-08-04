"""Discover real, unmodified local videos that cover regression-corpus gaps."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from src.services.pipeline_regression_corpus import (
    SUPPORTED_REGRESSION_VIDEO_EXTENSIONS,
    classify_probe,
    probe_video,
    sample_visual_features,
)


VIDEO_EXTENSIONS = SUPPORTED_REGRESSION_VIDEO_EXTENSIONS
TRUSTED_SOURCE_MARKERS = frozenset(
    {"raw", "download_staging", "regression_gap_staging"}
)
DERIVED_PATH_MARKERS = frozenset(
    {
        "render",
        "renders",
        "final",
        "output",
        "outputs",
        "export",
        "export_packages",
    }
)


class PipelineGapDiscoveryError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with _io_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _io_path(path: Path) -> Path:
    """Use the Windows extended-length prefix only at filesystem boundaries."""
    value = str(path)
    if os.name == "nt" and path.is_absolute() and not value.startswith("\\\\?\\"):
        return Path("\\\\?\\" + value)
    return path


def trusted_source_video(path: Path) -> bool:
    """Accept only source-like paths and reject known rendered/export trees."""
    parts = {part.lower() for part in path.parts}
    return bool(parts.intersection(TRUSTED_SOURCE_MARKERS)) and not bool(
        parts.intersection(DERIVED_PATH_MARKERS)
    )


def enumerate_source_videos(
    roots: Iterable[Path],
    *,
    workspace_root: Path,
) -> tuple[list[Path], list[str]]:
    workspace = workspace_root.resolve()
    accepted: set[Path] = set()
    excluded: list[str] = []
    for raw_root in roots:
        root = raw_root.resolve()
        if not root.is_relative_to(workspace):
            raise PipelineGapDiscoveryError(
                f"Source root must stay within workspace: {raw_root}"
            )
        if not root.is_dir():
            continue
        for raw_path in root.rglob("*"):
            if raw_path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            path = raw_path.resolve()
            if not path.is_relative_to(root) or not path.is_relative_to(workspace):
                continue
            if not _io_path(path).is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            if not trusted_source_video(path):
                excluded.append(relative)
                continue
            accepted.add(path)
    return sorted(accepted, key=lambda path: path.as_posix().lower()), sorted(excluded)


def discover_gap_candidates(
    *,
    video_paths: Iterable[Path],
    workspace_root: Path,
    target_gaps: Mapping[str, Iterable[str]],
    max_duration_seconds: float = 60.0,
    excluded_source_count: int = 0,
    probe_fn: Callable[[Path], dict[str, Any]] = probe_video,
    visual_fn: Callable[[Path], dict[str, Any]] = sample_visual_features,
) -> dict[str, Any]:
    """Hash-dedupe, probe and classify trusted real-video candidates."""
    workspace = workspace_root.resolve()
    targets: dict[str, list[str]] = {}
    for key, raw_values in target_gaps.items():
        values = sorted({str(value) for value in raw_values})
        if values:
            targets[str(key)] = values
    unique_by_sha: dict[str, Path] = {}
    duplicate_count = 0
    hash_failures: list[dict[str, str]] = []
    paths = sorted(
        {Path(path).resolve() for path in video_paths},
        key=lambda path: path.as_posix().lower(),
    )
    for path in paths:
        if not path.is_relative_to(workspace):
            raise PipelineGapDiscoveryError(
                f"Video path must stay within workspace: {path}"
            )
        try:
            digest = sha256_file(path)
        except OSError as exc:
            hash_failures.append(
                {
                    "path": path.relative_to(workspace).as_posix(),
                    "error": type(exc).__name__,
                }
            )
            continue
        if digest in unique_by_sha:
            duplicate_count += 1
            continue
        unique_by_sha[digest] = path

    candidates: list[dict[str, Any]] = []
    probe_failures: list[dict[str, str]] = []
    skipped_too_long = 0
    dimension_counts: dict[str, Counter[str]] = {
        key: Counter() for key in targets
    }
    for digest, path in sorted(
        unique_by_sha.items(), key=lambda item: item[1].as_posix().lower()
    ):
        relative = path.relative_to(workspace).as_posix()
        try:
            io_path = _io_path(path)
            probe = probe_fn(io_path)
            duration = float(probe.get("duration_seconds") or 0.0)
            if duration <= 0.0 or duration >= float(max_duration_seconds):
                skipped_too_long += 1
                continue
            visual = visual_fn(io_path)
        except Exception as exc:  # noqa: BLE001
            probe_failures.append(
                {"path": relative, "error": type(exc).__name__}
            )
            continue
        dimensions = classify_probe(probe)
        dimensions["lighting"] = str(visual.get("lighting") or "unknown")
        dimensions["motion"] = str(visual.get("motion") or "unknown")
        for key in dimension_counts:
            dimension_counts[key][str(dimensions.get(key) or "unknown")] += 1
        matches = [
            f"{key}:{dimensions.get(key)}"
            for key, values in targets.items()
            if str(dimensions.get(key) or "") in values
        ]
        if not matches:
            continue
        candidates.append(
            {
                "candidate_id": f"real_{digest[:16]}",
                "source_path": relative,
                "source_sha256": digest,
                "size_bytes": _io_path(path).stat().st_size,
                "matched_gaps": sorted(matches),
                "probe": probe,
                "visual_sample": visual,
                "dimensions": dimensions,
                "source_integrity": "ORIGINAL_BYTES_UNCHANGED",
                "status": "READY_FOR_OPERATOR_INTAKE_REVIEW",
            }
        )

    matched = {
        key: sorted(
            {
                str(candidate["dimensions"].get(key))
                for candidate in candidates
                if str(candidate["dimensions"].get(key) or "") in values
            }
        )
        for key, values in targets.items()
    }
    remaining = {
        key: sorted(set(values) - set(matched[key]))
        for key, values in targets.items()
        if set(values) - set(matched[key])
    }
    payload: dict[str, Any] = {
        "schema_version": "pipeline_gap_discovery_v1",
        "status": "CANDIDATES_FOUND" if candidates else "NO_MATCHING_REAL_SOURCES",
        "source_policy": {
            "trusted_path_markers": sorted(TRUSTED_SOURCE_MARKERS),
            "derived_path_markers_rejected": sorted(DERIVED_PATH_MARKERS),
            "dedupe": "sha256_original_bytes",
            "source_transformations": False,
            "synthetic_gap_evidence_allowed": False,
        },
        "target_gaps": targets,
        "max_duration_seconds": float(max_duration_seconds),
        "inventory": {
            "input_file_count": len(paths),
            "unique_source_count": len(unique_by_sha),
            "duplicate_file_count": duplicate_count,
            "hash_failure_count": len(hash_failures),
            "probe_failure_count": len(probe_failures),
            "too_long_or_invalid_duration_count": skipped_too_long,
            "derived_or_untrusted_excluded_count": max(
                0, int(excluded_source_count)
            ),
            "dimension_counts": {
                key: dict(sorted(counts.items()))
                for key, counts in dimension_counts.items()
            },
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "matched_gaps": matched,
        "remaining_gaps": remaining,
        "failures": {
            "hash": hash_failures,
            "probe": probe_failures,
        },
    }
    payload["discovery_sha256"] = _sha256_json(payload)
    return payload
