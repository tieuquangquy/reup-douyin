"""Build a hash-bound batch review pack from encoded Phase-4 residual CJK."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.build_phase2_residual_remediation_proposal import (
    cluster_residual_detections,
)
from scripts.run_phase4_adaptive import _source_path
from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    parse_localization_policy,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    apply_visual_remediation,
)


SCHEMA_VERSION = "phase4_output_residual_review_v1"
_SIGNATURE_RE = re.compile(r"[0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class OutputResidualReviewError(RuntimeError):
    pass


def output_stem_for_review_version(review_version: str) -> str:
    normalized = str(review_version or "").strip().lower()
    if not re.fullmatch(r"v\d+(?:_\d+)*", normalized):
        raise OutputResidualReviewError("Invalid review version")
    return f"phase4_output_residual_review_{normalized}"


def _signature(value: str) -> str:
    return "".join(_SIGNATURE_RE.findall(str(value or "")))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputResidualReviewError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise OutputResidualReviewError(f"{path.name} must contain an object")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    x = float(raw.get("x") or 0.0)
    y = float(raw.get("y") or 0.0)
    width = float(raw.get("width") or 0.0)
    height = float(raw.get("height") or 0.0)
    if (
        width <= 0
        or height <= 0
        or min(x, y) < 0
        or x + width > 1.001
        or y + height > 1.001
    ):
        raise OutputResidualReviewError("Residual geometry is invalid")
    return x, y, x + width, y + height


def _intersection_over_smaller(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    smaller = min(
        max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1]),
        max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1]),
    )
    return intersection / smaller if smaller > 0 else 0.0


def _suggestion_map(root: Path) -> dict[str, str]:
    path = root / "phase2_residual_translation_suggestions.json"
    if not path.is_file():
        return {}
    payload = _load_object(path)
    if (
        str(payload.get("status") or "") != "SUGGESTION_ONLY"
        or bool(payload.get("operator_approval_written"))
    ):
        raise OutputResidualReviewError("Residual translations are authoritative")
    return {
        str(row.get("ocr_text_corrected") or row.get("ocr_text") or ""): str(
            row.get("vi_text_suggested") or ""
        )
        for raw in list(payload.get("suggestions") or [])
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
        if str(row.get("ocr_text_corrected") or row.get("ocr_text") or "")
        and str(row.get("vi_text_suggested") or "")
    }


def classify_cluster(
    cluster: Mapping[str, Any],
    *,
    content_objects: Sequence[Mapping[str, Any]],
    render_tracks: Sequence[Mapping[str, Any]],
    suggestions: Mapping[str, str],
) -> dict[str, Any]:
    detections = [
        dict(row)
        for row in list(cluster.get("detections") or [])
        if isinstance(row, Mapping)
    ]
    if not detections:
        raise OutputResidualReviewError("Residual cluster is empty")
    representative = max(
        detections, key=lambda row: float(row.get("confidence") or 0.0)
    )
    observed = str(representative.get("text") or "").strip()
    signature = str(cluster.get("signature") or _signature(observed))
    frame_index = int(representative.get("frame_index") or 0)
    geometry = dict(representative.get("geometry") or {})
    residual_rect = _rect(geometry)
    contents = [dict(row) for row in content_objects if isinstance(row, Mapping)]
    exact = [
        row
        for row in contents
        if _signature(str(row.get("ocr_text_approved") or "")) == signature
    ]
    approved_tracks = [
        dict(row)
        for row in render_tracks
        if isinstance(row, Mapping)
        and str(row.get("translation_status") or "")
        in {"TRANSLATION_APPROVED", "TRANSLATION_DETERMINISTIC"}
        and str(row.get("text_vi") or "").strip()
    ]
    active_intersections: list[dict[str, Any]] = []
    for track in approved_tracks:
        if not (
            int(track.get("start_frame") or 0)
            <= frame_index
            <= int(track.get("end_frame") or -1)
        ):
            continue
        try:
            overlap = _intersection_over_smaller(
                residual_rect, _rect(dict(track.get("geometry") or {}))
            )
        except OutputResidualReviewError:
            continue
        if overlap >= 0.05:
            active_intersections.append(
                {
                    "text_id": track.get("text_id"),
                    "content_id": track.get("content_id"),
                    "overlap": round(overlap, 6),
                    "text_vi": track.get("text_vi"),
                }
            )
    if exact:
        content_ids = {str(row.get("content_id") or "") for row in exact}
        carry_tracks = [
            track
            for track in approved_tracks
            if str(track.get("content_id") or "") in content_ids
        ]
        render_values = sorted(
            {str(track.get("text_vi") or "").strip() for track in carry_tracks}
        )
        if len(render_values) == 1:
            return {
                "decision": "CARRY_FORWARD_APPROVED_CONTENT_COVERAGE",
                "source_text_suggested": str(exact[0].get("ocr_text_approved") or ""),
                "vi_text_suggested": render_values[0],
                "content_ids": sorted(content_ids),
                "active_intersections": active_intersections,
                "translation_authority": "EXISTING_EXACT_APPROVAL",
                "operator_approval_required": True,
            }
    nearest: tuple[float, dict[str, Any]] | None = None
    for row in contents:
        approved = str(row.get("ocr_text_approved") or "")
        approved_signature = _signature(approved)
        if not approved_signature:
            continue
        similarity = SequenceMatcher(None, signature, approved_signature).ratio()
        if nearest is None or similarity > nearest[0]:
            nearest = (similarity, row)
    confidence = float(representative.get("confidence") or 0.0)
    area = (residual_rect[2] - residual_rect[0]) * (
        residual_rect[3] - residual_rect[1]
    )
    if confidence < 0.60 and (area > 0.05 or len(detections) == 1):
        return {
            "decision": "FALSE_POSITIVE_REVIEW",
            "source_text_suggested": observed,
            "vi_text_suggested": None,
            "active_intersections": active_intersections,
            "translation_authority": "NONE",
            "operator_approval_required": True,
        }
    if nearest is not None and nearest[0] >= 0.75:
        content = nearest[1]
        content_id = str(content.get("content_id") or "")
        carry = [
            track
            for track in approved_tracks
            if str(track.get("content_id") or "") == content_id
        ]
        render_values = sorted(
            {str(track.get("text_vi") or "").strip() for track in carry}
        )
        return {
            "decision": "SOURCE_OCR_CORRECTION_AND_COVERAGE_REVIEW",
            "source_text_suggested": str(content.get("ocr_text_approved") or ""),
            "vi_text_suggested": render_values[0] if len(render_values) == 1 else None,
            "similarity": round(nearest[0], 6),
            "content_ids": [content_id] if content_id else [],
            "active_intersections": active_intersections,
            "translation_authority": (
                "EXISTING_NEAR_MATCH_REQUIRES_OCR_REVIEW"
                if len(render_values) == 1
                else "NONE"
            ),
            "operator_approval_required": True,
        }
    localization = parse_localization_policy(observed)
    if str(localization.get("mode") or "") == "deterministic":
        return {
            "decision": "DETERMINISTIC_LOCALIZATION_AND_COVERAGE_REVIEW",
            "source_text_suggested": observed,
            "vi_text_suggested": localization.get("render_text_suggested"),
            "active_intersections": active_intersections,
            "translation_authority": "DETERMINISTIC_CANDIDATE",
            "operator_approval_required": True,
        }
    suggested = str(suggestions.get(observed) or "").strip()
    return {
        "decision": (
            "TRANSLATION_SUGGESTION_AND_COVERAGE_REVIEW"
            if suggested
            else "TRANSLATION_INPUT_AND_COVERAGE_REVIEW"
        ),
        "source_text_suggested": observed,
        "vi_text_suggested": suggested or None,
        "active_intersections": active_intersections,
        "translation_authority": "SUGGESTION_ONLY" if suggested else "NONE",
        "operator_approval_required": True,
    }


def _load_frames(path: Path, frame_indices: Sequence[int]) -> dict[int, np.ndarray]:
    import cv2

    wanted = sorted({int(value) for value in frame_indices if int(value) >= 0})
    if not wanted:
        return {}
    targets = set(wanted)
    output: dict[int, np.ndarray] = {}
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise OutputResidualReviewError(f"Cannot open video: {path.name}")
    try:
        for frame_index in range(wanted[-1] + 1):
            ok, frame = capture.read()
            if not ok or frame is None:
                raise OutputResidualReviewError(
                    f"Cannot decode frame {frame_index}: {path.name}"
                )
            if frame_index in targets:
                output[frame_index] = frame
    finally:
        capture.release()
    return output


def _crop(image: np.ndarray, geometry: Mapping[str, Any]) -> np.ndarray:
    x0, y0, x1, y1 = _rect(geometry)
    height, width = image.shape[:2]
    pad_x = max(12, int(round((x1 - x0) * width * 0.25)))
    pad_y = max(12, int(round((y1 - y0) * height * 0.35)))
    px0 = max(0, int(math.floor(x0 * width)) - pad_x)
    py0 = max(0, int(math.floor(y0 * height)) - pad_y)
    px1 = min(width, int(math.ceil(x1 * width)) + pad_x)
    py1 = min(height, int(math.ceil(y1 * height)) + pad_y)
    return image[py0:py1, px0:px1]


def _write_contact(path: Path, source: np.ndarray, rendered: np.ndarray) -> float:
    import cv2

    if source.shape != rendered.shape or source.size == 0:
        raise OutputResidualReviewError("Residual evidence crops are incompatible")
    divider = np.full((source.shape[0], 8, 3), 255, dtype=np.uint8)
    contact = np.hstack([source, divider, rendered])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), contact):
        raise OutputResidualReviewError("Cannot write residual contact sheet")
    return float(
        np.abs(source.astype(np.float32) - rendered.astype(np.float32)).mean()
    )


def failed_residual_output_paths(case_root: Path) -> tuple[Path, Path] | None:
    """Prefer failed final QA, then fall back to failed visual-preview QA."""

    candidates = (
        (
            case_root / "qa" / "phase4_adaptive_final_output_qa.json",
            case_root / "phase4_adaptive_final.mp4",
        ),
        (
            case_root / "qa" / "phase4_adaptive_visual_preview_output_qa.json",
            case_root / "phase4_adaptive_visual_preview.mp4",
        ),
    )
    failed: list[tuple[Path, Path]] = []
    for qa_path, rendered_path in candidates:
        if not qa_path.is_file() or not rendered_path.is_file():
            continue
        qa = _load_object(qa_path)
        if (
            str(qa.get("status") or "") == "FAIL"
            and "residual_cjk" in list(qa.get("failed_checks") or [])
        ):
            failed.append((qa_path, rendered_path))
    return max(failed, key=lambda value: value[0].stat().st_mtime_ns) if failed else None


def refine_small_source_bound_cluster(
    recommendation: Mapping[str, Any],
    *,
    cluster: Mapping[str, Any],
    representative: Mapping[str, Any],
    crop_mean_abs_delta: float,
) -> dict[str, Any]:
    """Route tiny unchanged source/texture glyphs away from translation."""

    value = dict(recommendation)
    geometry = dict(representative.get("geometry") or {})
    signature = str(cluster.get("signature") or "").strip()
    if (
        value.get("decision") == "TRANSLATION_INPUT_AND_COVERAGE_REVIEW"
        and not list(value.get("active_intersections") or [])
        and 0 < len(signature) <= 2
        and float(geometry.get("width") or 0.0) <= 0.06
        and float(geometry.get("height") or 0.0) <= 0.12
        and float(geometry.get("y") or 0.0) < 0.78
        and float(crop_mean_abs_delta) <= 4.0
    ):
        value.update(
            {
                "decision": "FALSE_POSITIVE_REVIEW",
                "vi_text_suggested": None,
                "translation_authority": "NONE",
                "source_binding": "UNCHANGED_SMALL_SCENE_TEXTURE",
            }
        )
    return value


def build_review(
    run_root: str | Path,
    *,
    review_version: str = "V22_8",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    version = str(review_version or "").strip().upper()
    if not re.fullmatch(r"V[0-9]+(?:_[0-9]+)*", version):
        raise OutputResidualReviewError("Invalid residual review version")
    cases: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    for case_root in sorted(root.glob("local_*")):
        failed_output = failed_residual_output_paths(case_root)
        if failed_output is None:
            continue
        qa_path, rendered_path = failed_output
        input_path = case_root / "phase4_render_input.json"
        phase2_path = case_root / "phase2_ocr_timeline.json"
        meta_path = case_root / "phase4_adaptive_render_meta.json"
        if not all(
            path.is_file()
            for path in (qa_path, rendered_path, input_path, phase2_path, meta_path)
        ):
            continue
        qa = _load_object(qa_path)
        residual = dict(qa.get("residual_cjk") or {})
        detections = [
            dict(row)
            for row in list(residual.get("detections") or [])
            if isinstance(row, Mapping)
        ]
        clusters = cluster_residual_detections(detections)
        if not clusters:
            continue
        raw_contract = _load_object(input_path)
        contract, remediation_ref = apply_visual_remediation(
            case_root, raw_contract, contract_path=input_path
        )
        phase2 = _load_object(phase2_path)
        content_objects = [
            dict(row)
            for row in list(phase2.get("content_objects") or [])
            if isinstance(row, Mapping)
        ]
        suggestions = _suggestion_map(case_root)
        representatives = [
            max(
                list(cluster.get("detections") or []),
                key=lambda row: float(dict(row).get("confidence") or 0.0),
            )
            for cluster in clusters
        ]
        frame_indices = [int(dict(row).get("frame_index") or 0) for row in representatives]
        source_path = _source_path(case_root)
        source_frames = _load_frames(source_path, frame_indices)
        rendered_frames = _load_frames(rendered_path, frame_indices)
        evidence_dir = (
            case_root / "qa" / f"phase4_output_residual_review_{version.lower()}"
        )
        built_clusters: list[dict[str, Any]] = []
        for cluster, representative in zip(clusters, representatives):
            frame_index = int(dict(representative).get("frame_index") or 0)
            geometry = dict(dict(representative).get("geometry") or {})
            source_crop = _crop(source_frames[frame_index], geometry)
            rendered_crop = _crop(rendered_frames[frame_index], geometry)
            identity = hashlib.sha256(
                json.dumps(
                    {
                        "signature": cluster.get("signature"),
                        "geometry": geometry,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:12]
            cluster_id = f"outres_{identity}"
            contact_path = evidence_dir / f"{cluster_id}.jpg"
            crop_delta = _write_contact(contact_path, source_crop, rendered_crop)
            recommendation = classify_cluster(
                cluster,
                content_objects=content_objects,
                render_tracks=list(contract.get("render_tracks") or []),
                suggestions=suggestions,
            )
            recommendation = refine_small_source_bound_cluster(
                recommendation,
                cluster=cluster,
                representative=representative,
                crop_mean_abs_delta=crop_delta,
            )
            decision_counts[str(recommendation["decision"])] += 1
            built_clusters.append(
                {
                    "cluster_id": cluster_id,
                    "signature": cluster.get("signature"),
                    "detections": list(cluster.get("detections") or []),
                    "representative_frame_index": frame_index,
                    "recommendation": recommendation,
                    "evidence": {
                        "source_render_contact_sheet": {
                            "path": contact_path.relative_to(case_root).as_posix(),
                            "sha256": _sha256_file(contact_path),
                        },
                        "source_render_crop_mean_abs_delta": round(crop_delta, 6),
                    },
                }
            )
        cases.append(
            {
                "case_id": case_root.name,
                "authority_refs": {
                    "output_qa": {
                        "path": qa_path.relative_to(case_root).as_posix(),
                        "sha256": _sha256_file(qa_path),
                    },
                    "phase4_input": {
                        "path": input_path.name,
                        "sha256": _sha256_file(input_path),
                    },
                    "phase2_timeline": {
                        "path": phase2_path.name,
                        "sha256": _sha256_file(phase2_path),
                    },
                    "source_video": {
                        "path": source_path.name,
                        "sha256": _sha256_file(source_path),
                    },
                    "rendered_preview": {
                        "path": rendered_path.name,
                        "sha256": _sha256_file(rendered_path),
                    },
                    "visual_remediation": remediation_ref,
                },
                "clusters": built_clusters,
            }
        )
    if not cases:
        raise OutputResidualReviewError("No failed encoded residual CJK cases found")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "review_version": version,
        "status": "OUTPUT_RESIDUAL_REVIEW_REQUIRED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "counts": {
            "cases": len(cases),
            "clusters": sum(len(row["clusters"]) for row in cases),
            "decisions": dict(sorted(decision_counts.items())),
        },
        "cases": cases,
        "non_goals": [
            "do_not_write_translation_approval",
            "do_not_write_residual_remediation_authority",
            "do_not_relax_output_qa_thresholds",
            "do_not_overwrite_master_timeline",
        ],
    }
    token_seed = _sha256_json(payload)[:12].upper()
    payload["operator_review_token"] = (
        f"PHASE4_OUTPUT_RESIDUAL_REVIEW_APPROVED_{version}_{token_seed}"
    )
    payload["review_sha256"] = _sha256_json(payload)
    return payload


def _markdown(payload: Mapping[str, Any]) -> str:
    version = str(payload.get("review_version") or "V22_8").replace("_", ".")
    lines = [
        f"# Phase 4 Output Residual Review {version}",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Token: `{payload.get('operator_review_token')}`",
        f"- Review SHA-256: `{payload.get('review_sha256')}`",
        f"- Cases: `{dict(payload.get('counts') or {}).get('cases')}`",
        f"- Clusters: `{dict(payload.get('counts') or {}).get('clusters')}`",
        "- Proposal-only: `true`",
        "",
        "| Case | Cluster | Frame | Decision | Source | Vietnamese | Evidence |",
        "|---|---|---:|---|---|---|---|",
    ]
    for case in list(payload.get("cases") or []):
        for cluster in list(dict(case).get("clusters") or []):
            recommendation = dict(cluster.get("recommendation") or {})
            contact = dict(dict(cluster.get("evidence") or {}).get("source_render_contact_sheet") or {})
            lines.append(
                f"| `{case.get('case_id')}` | `{cluster.get('cluster_id')}` | "
                f"{cluster.get('representative_frame_index')} | "
                f"`{recommendation.get('decision')}` | "
                f"{str(recommendation.get('source_text_suggested') or '').replace('|', '/')} | "
                f"{str(recommendation.get('vi_text_suggested') or '').replace('|', '/')} | "
                f"`{contact.get('path')}` |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_output_residual_review"
    )
    parser.add_argument("run_root")
    parser.add_argument("--output-stem")
    parser.add_argument("--review-version", default="V22_8")
    args = parser.parse_args()
    try:
        root = Path(args.run_root).resolve()
        review_version = str(args.review_version or "").strip()
        stem = str(
            args.output_stem or output_stem_for_review_version(review_version)
        ).strip()
        if not stem or Path(stem).name != stem:
            raise OutputResidualReviewError("Invalid output stem")
        payload = build_review(root, review_version=review_version)
        json_path = root / f"{stem}.json"
        markdown_path = root / f"{stem}.md"
        _write_json_atomic(json_path, payload)
        _write_text_atomic(markdown_path, _markdown(payload))
    except (OSError, ValueError, OutputResidualReviewError) as exc:
        print(f"[PHASE4-OUTPUT-RESIDUAL-REVIEW][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "counts": payload["counts"],
                "operator_review_token": payload["operator_review_token"],
                "review_sha256": payload["review_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
