"""Build the immutable Phase 4 input and representative still-image preflight."""

from __future__ import annotations

import json
import logging
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.core.settings import get_settings
from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
)
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    _detect_residual_cjk,
    build_local_residual_ocr_provider,
    classify_editor_caption_ocr_false_positives,
    classify_source_intrinsic_edge_cjk,
    classify_source_scene_protected_cjk,
    classify_temporally_unconfirmed_cjk,
)
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    apply_residual_cjk_false_positive_approval,
    load_residual_cjk_false_positive_approval,
    residual_detection_sha256,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    prepare_phase4_from_root,
    write_phase4_preflight_artifacts,
)
from src.media_pipeline.video_renderer.reference_plate import (
    is_usable_reference_plate_candidate,
    reference_plate_candidate_score,
)
from src.media_pipeline.video_renderer.render_authority import (
    apply_pts_map_to_contract,
    build_reproducible_render_recipe,
    probe_media_authority,
    resolve_audio_authority,
)

logger = logging.getLogger(__name__)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_residual_false_positive_approval(
    root: Path,
    contract: Mapping[str, Any],
) -> dict[str, Any] | None:
    try:
        return load_residual_cjk_false_positive_approval(
            root_dir=root,
            contract=contract,
        )
    except Phase4ApprovalError as exc:
        raise Phase4InputError(str(exc)) from exc


def _apply_residual_false_positive_approval(
    detections: Sequence[Mapping[str, Any]],
    approval: Mapping[str, Any] | None,
    *,
    fps: float = 30.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        return apply_residual_cjk_false_positive_approval(
            detections,
            approval,
            fps=fps,
        )
    except Phase4ApprovalError as exc:
        raise Phase4InputError(str(exc)) from exc


def _quarantine_previous_preflight_samples(sample_dir: Path, *, root: Path) -> int:
    """Keep one unambiguous current sample set while preserving old evidence."""
    previous = [path for path in sample_dir.iterdir() if path.is_file()]
    if not previous:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stale_dir = root / "qa" / "stale" / "phase4_preflight_samples" / stamp
    stale_dir.mkdir(parents=True, exist_ok=False)
    moved = 0
    for path in previous:
        # Two retrying workers can observe the same directory during a crash
        # recovery window.  Quarantine is evidence housekeeping; a file that
        # disappeared after the snapshot must not turn a deterministic render
        # gate into an opaque FileNotFoundError.
        try:
            path.replace(stale_dir / path.name)
            moved += 1
        except FileNotFoundError:
            continue
    return moved


def _runtime_versions() -> dict[str, str]:
    import cv2
    import PIL

    ffmpeg_version = "unknown"
    try:
        completed = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if completed.returncode == 0 and completed.stdout:
            ffmpeg_version = completed.stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "opencv": str(cv2.__version__),
        "numpy": str(np.__version__),
        "pillow": str(PIL.__version__),
        "ffmpeg": ffmpeg_version,
    }


def _representative_frames(
    contract: Mapping[str, Any], report: Mapping[str, Any], *, limit: int = 5
) -> list[int]:
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    localized = [row for row in tracks if str(row.get("text_vi") or "").strip()]
    if not localized:
        return []

    def stable_frame(row: Mapping[str, Any]) -> int:
        start = int(row.get("start_frame") or 0)
        end = int(row.get("end_frame") or start)
        raw_best = row.get("best_frame_index")
        best = int(raw_best) if raw_best is not None else (start + end) // 2
        return best if start <= best <= end else (start + end) // 2

    selected: list[int] = [stable_frame(localized[0])]

    metrics = [
        dict(row)
        for row in list(report.get("track_metrics") or [])
        if isinstance(row, Mapping)
    ]
    if metrics:
        longest_id = str(
            max(metrics, key=lambda row: int(row.get("glyph_width_px") or 0)).get(
                "text_id"
            )
            or ""
        )
        longest = next(
            (row for row in localized if str(row.get("text_id") or "") == longest_id),
            None,
        )
        if longest is not None:
            selected.append(stable_frame(longest))

    by_content: dict[str, list[dict[str, Any]]] = {}
    for row in localized:
        by_content.setdefault(str(row.get("content_id") or ""), []).append(row)
    duplicate = next((rows for rows in by_content.values() if len(rows) > 1), None)
    if duplicate:
        selected.extend(stable_frame(row) for row in duplicate[:2])

    event_frames = sorted({int(row.get("start_frame") or 0) for row in localized})
    if event_frames:
        busiest = max(
            event_frames,
            key=lambda frame: sum(
                int(row.get("start_frame") or 0)
                <= frame
                <= int(row.get("end_frame") or 0)
                for row in localized
            ),
        )
        busiest_rows = [
            row
            for row in localized
            if int(row.get("start_frame") or 0)
            <= busiest
            <= int(row.get("end_frame") or 0)
        ]
        if busiest_rows:
            overlap_start = max(
                int(row.get("start_frame") or 0) for row in busiest_rows
            )
            overlap_end = min(
                int(row.get("end_frame") or overlap_start)
                for row in busiest_rows
            )
            stable = stable_frame(busiest_rows[0])
            selected.append(
                stable
                if overlap_start <= stable <= overlap_end
                else (overlap_start + max(overlap_start, overlap_end)) // 2
            )
    selected.append(stable_frame(localized[-1]))
    unique = list(dict.fromkeys(selected))
    frame_count = int(dict(contract.get("video") or {}).get("frame_count") or 0)
    capacity = max(1, int(limit))
    if frame_count < 1:
        return unique[:capacity]
    first = 0
    last = frame_count - 1
    if capacity == 1 or first == last:
        return [first]
    middle = [index for index in unique if index not in {first, last}]
    return [first, *middle[: max(0, capacity - 2)], last]


def _reference_candidate_indices(
    track: Mapping[str, Any], *, frame_count: int, fps: float
) -> list[int]:
    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    offsets = {
        1,
        max(1, int(round(float(fps) * 0.10))),
        max(1, int(round(float(fps) * 0.25))),
        max(1, int(round(float(fps) * 0.50))),
    }
    return [
        index
        for offset in sorted(offsets)
        for index in (start - offset, end + offset)
        if 0 <= index < frame_count
    ]


def _decode_frames_sequential(
    capture: Any, frame_indices: Sequence[int]
) -> dict[int, Any]:
    """Decode exact frame numbers without unreliable random seeks on VFR media."""
    targets = sorted({int(index) for index in frame_indices if int(index) >= 0})
    if not targets:
        return {}
    wanted = set(targets)
    decoded: dict[int, Any] = {}
    for frame_index in range(targets[-1] + 1):
        ok, frame = capture.read()
        if not ok or frame is None:
            raise Phase4InputError(
                f"Cannot sequentially decode source frame {frame_index}"
            )
        if frame_index in wanted:
            decoded[frame_index] = frame
    return decoded


def _reference_frame_for_track(
    decoded_frames: Mapping[int, np.ndarray],
    track: Mapping[str, Any],
    *,
    current_frame: np.ndarray,
    frame_count: int,
    fps: float,
) -> tuple[int, np.ndarray] | None:
    candidates = _reference_candidate_indices(
        track, frame_count=frame_count, fps=fps
    )
    if not candidates:
        return None
    policy = dict(track.get("render_policy") or {})
    cover = dict(policy.get("cover") or {})
    roi = dict(cover.get("roi") or {})
    height, width = current_frame.shape[:2]
    x0 = max(0, int(round(float(roi.get("x") or 0.0) * width)))
    y0 = max(0, int(round(float(roi.get("y") or 0.0) * height)))
    x1 = min(width, int(round((float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0)) * width)))
    y1 = min(height, int(round((float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)) * height)))
    outside = np.ones((height, width), dtype=bool)
    outside[y0:y1, x0:x1] = False
    inside = ~outside
    choices: list[tuple[float, float, int, np.ndarray]] = []
    for index in candidates:
        candidate = decoded_frames.get(index)
        if candidate is None or candidate.shape != current_frame.shape:
            continue
        mad = (
            float(
                np.abs(
                    candidate[outside].astype(np.float32)
                    - current_frame[outside].astype(np.float32)
                ).mean()
            )
            if np.any(outside)
            else 255.0
        )
        inside_mad = (
            float(
                np.abs(
                    candidate[inside].astype(np.float32)
                    - current_frame[inside].astype(np.float32)
                ).mean()
            )
            if np.any(inside)
            else 0.0
        )
        if not is_usable_reference_plate_candidate(
            outside_mad=mad,
            inside_mad=inside_mad,
        ):
            continue
        score = reference_plate_candidate_score(
            outside_mad=mad,
            inside_mad=inside_mad,
        )
        choices.append((score, mad, index, candidate))
    if not choices:
        return None
    _score, outside_mad, index, candidate = min(
        choices, key=lambda item: item[0]
    )
    # A reference from a different intro/scene is worse than bounded spatial
    # inpaint. Do not seed a plate that cannot align to the surrounding frame.
    if outside_mad > 24.0:
        return None
    return index, candidate


def write_preflight_samples(
    *,
    root_dir: str | Path,
    source_video: str | Path,
    contract: Mapping[str, Any],
    report: Mapping[str, Any],
    limit: int = 5,
    required_frame_indices: Sequence[int] = (),
) -> list[Path]:
    import cv2
    import numpy as np

    root = Path(root_dir)
    source = Path(source_video)
    video = dict(contract.get("video") or {})
    expected_width = int(video.get("frame_width") or 0)
    expected_height = int(video.get("frame_height") or 0)
    expected_count = int(video.get("frame_count") or 0)
    expected_fps = float(video.get("fps") or 0.0)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise Phase4InputError("Cannot open source video for Phase 4 preflight")
    actual_width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    actual_height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    actual_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    actual_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    if (
        (actual_width, actual_height) != (expected_width, expected_height)
        or abs(actual_count - expected_count) > 2
        or abs(actual_fps - expected_fps) > 0.5
    ):
        capture.release()
        raise Phase4InputError("Source video metadata does not match Phase 1 authority")

    sample_dir = root / "qa" / "phase4_preflight_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    _quarantine_previous_preflight_samples(sample_dir, root=root)
    frames = _representative_frames(contract, report, limit=limit)
    frames = list(
        dict.fromkeys(
            [
                *frames,
                *(
                    int(index)
                    for index in required_frame_indices
                    if 0 <= int(index) < expected_count
                ),
            ]
        )
    )
    tracks = [dict(row) for row in list(contract.get("render_tracks") or [])]
    reference_indices: set[int] = set()
    for frame_index in frames:
        for row in tracks:
            if not (
                int(row.get("start_frame") or 0)
                <= frame_index
                <= int(row.get("end_frame") or 0)
            ):
                continue
            policy = dict(row.get("render_policy") or {})
            if (
                str(dict(policy.get("cover") or {}).get("mask_mode") or "")
                == "stylized_components"
            ):
                reference_indices.update(
                    _reference_candidate_indices(
                        row,
                        frame_count=expected_count,
                        fps=expected_fps,
                    )
                )
    font = resolve_drawtext_font()
    adaptive = AdaptiveFrameRenderer(fontfile=font)
    seeded_references: dict[str, int] = {}
    outputs: list[Path] = []
    sheet_tiles: list[Any] = []
    manifest_rows: list[dict[str, Any]] = []
    try:
        decoded_frames = _decode_frames_sequential(
            capture, [*frames, *reference_indices]
        )
        for frame_index in frames:
            frame = decoded_frames.get(frame_index)
            if frame is None:
                raise Phase4InputError(
                    f"Cannot decode representative frame {frame_index}"
                )
            active_rows = [
                row
                for row in tracks
                if int(row.get("start_frame") or 0)
                <= frame_index
                <= int(row.get("end_frame") or 0)
            ]
            for row in active_rows:
                text_id = str(row.get("text_id") or "")
                policy = dict(row.get("render_policy") or {})
                mask_mode = str(
                    dict(policy.get("cover") or {}).get("mask_mode") or ""
                )
                if (
                    not text_id
                    or text_id in seeded_references
                    or mask_mode != "stylized_components"
                ):
                    continue
                reference = _reference_frame_for_track(
                    decoded_frames,
                    row,
                    current_frame=frame,
                    frame_count=expected_count,
                    fps=expected_fps,
                )
                if reference is not None:
                    reference_index, reference_frame = reference
                    adaptive.seed_reference(text_id, reference_frame)
                    seeded_references[text_id] = reference_index
                    reference_path = sample_dir / (
                        f"reference_{text_id}_f{reference_index:06d}.jpg"
                    )
                    if cv2.imwrite(str(reference_path), reference_frame):
                        outputs.append(reference_path)
            union_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            for row in active_rows:
                union_mask = cv2.bitwise_or(
                    union_mask,
                    adaptive.mask_builder(frame, row),
                )
            try:
                rendered, frame_qa = adaptive.render_frame(frame, active_rows)
            except AdaptiveRenderBlocked as exc:
                blocked_path = sample_dir / f"frame_{frame_index:06d}_blocked.json"
                _write_json_atomic(
                    blocked_path,
                    {
                        "frame_index": frame_index,
                        "active_text_ids": [row.get("text_id") for row in active_rows],
                        "reason": str(exc),
                        "diagnostics": exc.diagnostics,
                    },
                )
                raise Phase4InputError(
                    f"Adaptive visual preflight blocked at frame {frame_index}"
                ) from exc
            path = sample_dir / f"frame_{frame_index:06d}.jpg"
            if not cv2.imwrite(str(path), rendered):
                raise Phase4InputError("Cannot write Phase 4 preflight sample")
            outputs.append(path)
            mask_visual = frame.copy()
            red = np.zeros_like(frame)
            red[:, :, 2] = 255
            selected = union_mask > 0
            if np.any(selected):
                mask_visual[selected] = (
                    0.45 * mask_visual[selected].astype(np.float32)
                    + 0.55 * red[selected].astype(np.float32)
                ).astype(np.uint8)
            triptych = np.hstack([frame, mask_visual, rendered])
            triptych_path = sample_dir / f"frame_{frame_index:06d}_before_mask_after.jpg"
            if not cv2.imwrite(str(triptych_path), triptych):
                raise Phase4InputError("Cannot write Phase 4 before/mask/after sample")
            outputs.append(triptych_path)
            qa_path = sample_dir / f"frame_{frame_index:06d}_qa.json"
            _write_json_atomic(qa_path, frame_qa)
            outputs.append(qa_path)
            tile_width = 640
            tile_height = max(1, int(round(rendered.shape[0] * tile_width / rendered.shape[1])))
            tile = cv2.resize(rendered, (tile_width, tile_height))
            cv2.putText(
                tile,
                f"frame={frame_index} active={len(active_rows)}",
                (14, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            sheet_tiles.append(tile)
            manifest_rows.append(
                {
                    "frame_index": frame_index,
                    "active_text_ids": [row.get("text_id") for row in active_rows],
                    "path": path.relative_to(root).as_posix(),
                    "triptych_path": triptych_path.relative_to(root).as_posix(),
                    "qa_path": qa_path.relative_to(root).as_posix(),
                    "reference_frames": {
                        str(row.get("text_id") or ""): seeded_references.get(
                            str(row.get("text_id") or "")
                        )
                        for row in active_rows
                        if str(row.get("text_id") or "") in seeded_references
                    },
                }
            )
    finally:
        capture.release()

    if sheet_tiles:
        max_height = max(tile.shape[0] for tile in sheet_tiles)
        padded: list[Any] = []
        for tile in sheet_tiles:
            if tile.shape[0] < max_height:
                pad = np.full(
                    (max_height - tile.shape[0], tile.shape[1], 3), 32, dtype=np.uint8
                )
                tile = np.vstack([tile, pad])
            padded.append(tile)
        contact = np.hstack(padded)
        contact_path = sample_dir / "contact_sheet.jpg"
        if not cv2.imwrite(str(contact_path), contact):
            raise Phase4InputError("Cannot write Phase 4 preflight contact sheet")
        outputs.append(contact_path)
    manifest_path = sample_dir / "sample_manifest.json"
    _write_json_atomic(manifest_path, {"samples": manifest_rows})
    outputs.append(manifest_path)
    return outputs


def write_residual_temporal_confirmation_samples(
    *,
    root_dir: str | Path,
    source_video: str | Path,
    contract: Mapping[str, Any],
    frame_indices: Sequence[int],
) -> dict[int, Path]:
    """Render adjacent frames so one-frame OCR hallucinations do not block preflight."""

    import cv2

    root = Path(root_dir)
    source = Path(source_video)
    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    fps = float(video.get("fps") or 0.0)
    targets = sorted(
        {
            int(index)
            for index in frame_indices
            if 0 <= int(index) < frame_count
        }
    )
    if not targets or frame_count < 1 or fps <= 0:
        return {}
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    reference_indices: set[int] = set()
    for frame_index in targets:
        for row in tracks:
            if not (
                int(row.get("start_frame") or 0)
                <= frame_index
                <= int(row.get("end_frame") or 0)
            ):
                continue
            policy = dict(row.get("render_policy") or {})
            if (
                str(dict(policy.get("cover") or {}).get("mask_mode") or "")
                == "stylized_components"
            ):
                reference_indices.update(
                    _reference_candidate_indices(
                        row,
                        frame_count=frame_count,
                        fps=fps,
                    )
                )
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise Phase4InputError(
            "Cannot open source video for residual temporal confirmation"
        )
    try:
        decoded = _decode_frames_sequential(
            capture,
            [*targets, *reference_indices],
        )
    finally:
        capture.release()
    adaptive = AdaptiveFrameRenderer(fontfile=resolve_drawtext_font())
    seeded: set[str] = set()
    output_dir = (
        root
        / "qa"
        / "phase4_preflight_samples"
        / "residual_temporal_confirmation"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[int, Path] = {}
    for frame_index in targets:
        frame = decoded.get(frame_index)
        if frame is None:
            raise Phase4InputError(
                f"Cannot decode residual confirmation frame {frame_index}"
            )
        active_rows = [
            row
            for row in tracks
            if int(row.get("start_frame") or 0)
            <= frame_index
            <= int(row.get("end_frame") or 0)
        ]
        for row in active_rows:
            text_id = str(row.get("text_id") or "")
            policy = dict(row.get("render_policy") or {})
            if (
                not text_id
                or text_id in seeded
                or str(dict(policy.get("cover") or {}).get("mask_mode") or "")
                != "stylized_components"
            ):
                continue
            reference = _reference_frame_for_track(
                decoded,
                row,
                current_frame=frame,
                frame_count=frame_count,
                fps=fps,
            )
            if reference is not None:
                _reference_index, reference_frame = reference
                adaptive.seed_reference(text_id, reference_frame)
                seeded.add(text_id)
        try:
            rendered, _frame_qa = adaptive.render_frame(frame, active_rows)
        except AdaptiveRenderBlocked as exc:
            raise Phase4InputError(
                f"Residual confirmation render blocked at frame {frame_index}"
            ) from exc
        path = output_dir / f"frame_{frame_index:06d}.jpg"
        if not cv2.imwrite(str(path), rendered):
            raise Phase4InputError(
                "Cannot write residual temporal confirmation sample"
            )
        outputs[frame_index] = path
    return outputs


def write_source_residual_samples(
    *,
    root_dir: str | Path,
    source_video: str | Path,
    frame_indices: Sequence[int],
) -> dict[int, Path]:
    """Materialize exact source frames for provenance-bound residual OCR.

    Temporal persistence alone cannot distinguish real residual CJK from a
    stable bracelet, logo, food texture, or filmed-device glyph that the local
    recognizer happens to decode as Chinese.  Keeping source samples beside the
    rendered samples lets preflight apply the same pixel-bound provenance
    checks as encoded-output QA.
    """

    import cv2

    root = Path(root_dir)
    source = Path(source_video)
    targets = sorted({int(index) for index in frame_indices if int(index) >= 0})
    if not targets:
        return {}
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise Phase4InputError("Cannot open source video for residual provenance")
    try:
        decoded = _decode_frames_sequential(capture, targets)
    finally:
        capture.release()
    output_dir = (
        root
        / "qa"
        / "phase4_preflight_samples"
        / "residual_source_confirmation"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[int, Path] = {}
    for frame_index in targets:
        frame = decoded.get(frame_index)
        if frame is None:
            raise Phase4InputError(
                f"Cannot decode residual source frame {frame_index}"
            )
        path = output_dir / f"frame_{frame_index:06d}.jpg"
        if not cv2.imwrite(str(path), frame):
            raise Phase4InputError("Cannot write residual source confirmation frame")
        outputs[frame_index] = path
    return outputs


def run(root_dir: str | Path) -> int:
    root = Path(root_dir).resolve()
    contract, report, source = prepare_phase4_from_root(root)
    residual_false_positive_approval = _load_residual_false_positive_approval(
        root,
        contract,
    )
    media_authority = probe_media_authority(source)
    frame_timestamps = list(media_authority.pop("frame_timestamps_seconds", []) or [])
    manifest_path = root / "render_prep_manifest.json"
    render_prep_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else None
    )
    audio_authority = resolve_audio_authority(
        render_prep_manifest,
        allow_source_passthrough=True,
    )
    timebase_authority = dict(media_authority.get("timebase") or {})
    color_authority = dict(media_authority.get("video") or {})
    expected_frame_count = int(
        dict(contract.get("video") or {}).get("frame_count") or 0
    )
    if frame_timestamps and expected_frame_count:
        decoded_frame_count = len(frame_timestamps)
        if decoded_frame_count != expected_frame_count and abs(
            decoded_frame_count - expected_frame_count
        ) <= 2:
            contract.setdefault("video", {})["frame_count"] = decoded_frame_count
            report["frame_count_reconciliation"] = {
                "status": "RECONCILED_TO_MEDIA_PROBE",
                "phase1_frame_count": expected_frame_count,
                "decoded_frame_count": decoded_frame_count,
                "delta": decoded_frame_count - expected_frame_count,
            }
    pts_map_path: Path | None = None
    if (
        str(timebase_authority.get("status") or "") == "PTS_RENDER_REQUIRED"
        and len(frame_timestamps) >= int(dict(contract.get("video") or {}).get("frame_count") or 0)
    ):
        contract = apply_pts_map_to_contract(contract, frame_timestamps)
        pts_map_path = root / "phase4_pts_map.json"
        _write_json_atomic(
            pts_map_path,
            {
                "schema_version": "phase4_pts_map_v1",
                "source_video_sha256": dict(
                    dict(contract.get("refs") or {}).get("source_video_ref") or {}
                ).get("sha256"),
                "frame_count": len(frame_timestamps),
                "timestamps_seconds": frame_timestamps,
            },
        )
        timebase_authority = {
            **timebase_authority,
            "status": "READY_WITH_PTS_MAP",
            "pts_map_ref": {
                "path": pts_map_path.name,
                "sha256": _sha256_file(pts_map_path),
            },
        }
        contract.setdefault("refs", {})["pts_map_ref"] = timebase_authority[
            "pts_map_ref"
        ]
    final_render_gate = "READY_FOR_FINAL_RENDER"
    if str(timebase_authority.get("status") or "") not in {
        "READY",
        "READY_WITH_PTS_MAP",
    }:
        final_render_gate = "BLOCKED_TIMEBASE_AUTHORITY"
        report["status"] = "PHASE4_PREFLIGHT_BLOCKED"
        report.setdefault("blocked_reasons", []).append("pts_render_required")
        contract["status"] = "PHASE4_PREFLIGHT_BLOCKED"
    elif str(audio_authority.get("status") or "") != "READY":
        final_render_gate = "BLOCKED_AUDIO_AUTHORITY"
    contract["authorities"] = {
        "timebase": timebase_authority,
        "audio": audio_authority,
        "color": color_authority,
    }
    contract["final_render_gate"] = final_render_gate
    report["authority_summary"] = {
        "timebase": timebase_authority.get("status"),
        "audio": audio_authority.get("status"),
        "final_render_gate": final_render_gate,
    }
    write_phase4_preflight_artifacts(
        root_dir=root,
        contract=contract,
        report=report,
    )
    required_residual_frames = (
        [
            int(
                dict(residual_false_positive_approval.get("detection") or {}).get(
                    "frame_index"
                )
                or 0
            )
        ]
        if residual_false_positive_approval is not None
        else []
    )
    samples = write_preflight_samples(
        root_dir=root,
        source_video=source,
        contract=contract,
        report=report,
        required_frame_indices=required_residual_frames,
    )
    rendered_sample_paths: dict[int, Path] = {}
    sample_pattern = re.compile(r"^frame_(\d{6})\.jpg$")
    for path in samples:
        match = sample_pattern.fullmatch(path.name)
        if match:
            rendered_sample_paths[int(match.group(1))] = path
    residual_ocr_complete = True
    residual_cjk: list[dict[str, Any]] = []
    residual_ocr_error: str | None = None
    residual_provider_name: str | None = None
    raw_residual_cjk: list[dict[str, Any]] = []
    source_residual_cjk: list[dict[str, Any]] = []
    source_scene_protected_cjk: list[dict[str, Any]] = []
    source_intrinsic_false_positives: list[dict[str, Any]] = []
    editor_caption_ocr_false_positives: list[dict[str, Any]] = []
    temporal_confirmation_cjk: list[dict[str, Any]] = []
    temporal_false_positives: list[dict[str, Any]] = []
    operator_false_positive_exclusions: list[dict[str, Any]] = []
    source_residual_paths: dict[int, Path] = {}
    temporal_confirmation_paths: dict[int, Path] = {}
    if rendered_sample_paths:
        try:
            residual_provider = build_local_residual_ocr_provider()
            residual_provider_name = str(
                getattr(residual_provider, "provider_name", "local_residual_ocr")
            )
            (
                residual_ocr_complete,
                raw_residual_cjk,
                residual_ocr_error,
            ) = _detect_residual_cjk(
                provider=residual_provider,
                rendered_paths=rendered_sample_paths,
                fps=float(dict(contract.get("video") or {}).get("fps") or 30.0),
            )
            residual_cjk = list(raw_residual_cjk)
            frame_count = int(dict(contract.get("video") or {}).get("frame_count") or 0)
            if residual_ocr_complete and raw_residual_cjk:
                raw_frame_indices = sorted(
                    {int(row.get("frame_index") or 0) for row in raw_residual_cjk}
                )
                source_residual_paths = write_source_residual_samples(
                    root_dir=root,
                    source_video=source,
                    frame_indices=raw_frame_indices,
                )
                (
                    source_complete,
                    source_residual_cjk,
                    source_error,
                ) = _detect_residual_cjk(
                    provider=residual_provider,
                    rendered_paths=source_residual_paths,
                    fps=float(
                        dict(contract.get("video") or {}).get("fps") or 30.0
                    ),
                )
                residual_ocr_complete = residual_ocr_complete and source_complete
                residual_ocr_error = residual_ocr_error or source_error
                if source_complete:
                    import cv2

                    source_frames = {
                        frame_index: cv2.imread(str(path), cv2.IMREAD_COLOR)
                        for frame_index, path in source_residual_paths.items()
                    }
                    rendered_frames = {
                        frame_index: cv2.imread(str(path), cv2.IMREAD_COLOR)
                        for frame_index, path in rendered_sample_paths.items()
                        if frame_index in source_residual_paths
                    }
                    residual_cjk, source_scene_protected_cjk = (
                        classify_source_scene_protected_cjk(
                            residual_cjk,
                            contract=contract,
                            source_detections=source_residual_cjk,
                            source_frames=source_frames,
                            rendered_frames=rendered_frames,
                        )
                    )
                    residual_cjk, source_intrinsic_false_positives = (
                        classify_source_intrinsic_edge_cjk(
                            residual_cjk,
                            source_residual_cjk,
                            contract=contract,
                            source_frames=source_frames,
                            rendered_frames=rendered_frames,
                        )
                    )
                    residual_cjk, editor_caption_ocr_false_positives = (
                        classify_editor_caption_ocr_false_positives(
                            residual_cjk,
                            contract=contract,
                            source_frames=source_frames,
                            rendered_frames=rendered_frames,
                        )
                    )
            if residual_ocr_complete and residual_cjk and frame_count > 0:
                confirmation_indices = sorted(
                    {
                        neighbor
                        for row in residual_cjk
                        for neighbor in (
                            int(row.get("frame_index") or 0) - 1,
                            int(row.get("frame_index") or 0) + 1,
                        )
                        if 0 <= neighbor < frame_count
                    }
                )
                temporal_confirmation_paths = (
                    write_residual_temporal_confirmation_samples(
                        root_dir=root,
                        source_video=source,
                        contract=contract,
                        frame_indices=confirmation_indices,
                    )
                )
                (
                    temporal_complete,
                    temporal_confirmation_cjk,
                    temporal_error,
                ) = _detect_residual_cjk(
                    provider=residual_provider,
                    rendered_paths=temporal_confirmation_paths,
                    fps=float(
                        dict(contract.get("video") or {}).get("fps") or 30.0
                    ),
                )
                residual_ocr_complete = residual_ocr_complete and temporal_complete
                residual_ocr_error = residual_ocr_error or temporal_error
                if temporal_complete:
                    (
                        residual_cjk,
                        temporal_false_positives,
                    ) = classify_temporally_unconfirmed_cjk(
                        residual_cjk,
                        temporal_confirmation_cjk,
                        contract=contract,
                        frame_count=frame_count,
                        source_detections=source_residual_cjk,
                    )
            if residual_ocr_complete and residual_false_positive_approval is not None:
                (
                    residual_cjk,
                    operator_false_positive_exclusions,
                ) = _apply_residual_false_positive_approval(
                    residual_cjk,
                    residual_false_positive_approval,
                    fps=float(dict(contract.get("video") or {}).get("fps") or 30.0),
                )
        except Exception as exc:  # Fail closed without exposing provider details.
            residual_ocr_complete = False
            residual_ocr_error = f"local_ocr_provider_failed:{type(exc).__name__}"
    report["residual_cjk_preflight"] = {
        "policy_version": "source_bound_temporal_cjk_confirmation_v2",
        "provider": residual_provider_name,
        "complete": residual_ocr_complete,
        "error": residual_ocr_error,
        "sampled_frames": sorted(rendered_sample_paths),
        "detections": residual_cjk,
        "raw_detections": raw_residual_cjk,
        "source_detections": source_residual_cjk,
        "source_scene_protected": source_scene_protected_cjk,
        "source_intrinsic_false_positives": source_intrinsic_false_positives,
        "editor_caption_ocr_false_positives": editor_caption_ocr_false_positives,
        "temporal_confirmation_detections": temporal_confirmation_cjk,
        "temporal_false_positives": temporal_false_positives,
        "operator_false_positive_exclusions": operator_false_positive_exclusions,
        "temporal_confirmation_frames": [
            path.relative_to(root).as_posix()
            for _index, path in sorted(temporal_confirmation_paths.items())
        ],
        "source_confirmation_frames": [
            path.relative_to(root).as_posix()
            for _index, path in sorted(source_residual_paths.items())
        ],
    }
    if not residual_ocr_complete or residual_cjk:
        report["status"] = "PHASE4_PREFLIGHT_BLOCKED"
        contract["status"] = "PHASE4_PREFLIGHT_BLOCKED"
        reason = (
            "residual_cjk_ocr_incomplete"
            if not residual_ocr_complete
            else f"residual_cjk:{len(residual_cjk)}"
        )
        report.setdefault("blocked_reasons", []).append(reason)
        contract["final_render_gate"] = "BLOCKED_VISUAL_RESIDUAL_CJK"
        final_render_gate = "BLOCKED_VISUAL_RESIDUAL_CJK"
        report.setdefault("authority_summary", {})[
            "final_render_gate"
        ] = final_render_gate
    # Rewrite the contract/report after residual OCR so a previously READY
    # typography-only artifact cannot survive a visual-CJK failure.
    write_phase4_preflight_artifacts(
        root_dir=root,
        contract=contract,
        report=report,
    )
    input_path = (
        root / "phase4_render_input.json"
        if (root / "phase4_render_input.json").is_file()
        else root / "phase4_render_input_preview.json"
    )
    font = resolve_drawtext_font()
    source_ref = dict(
        dict(contract.get("refs") or {}).get("source_video_ref") or {}
    )
    settings = get_settings()
    recipe = build_reproducible_render_recipe(
        phase4_input_sha256=_sha256_file(input_path),
        source_video_sha256=str(source_ref.get("sha256") or _sha256_file(source)),
        font_sha256=_sha256_file(font),
        policy_version=str(contract.get("render_policy_version") or "unknown"),
        runtime_versions=_runtime_versions(),
        audio_authority=audio_authority,
        color_authority=color_authority,
        timebase_authority=timebase_authority,
        anti_transform_enabled=False,
        anti_seed=None,
        encoding_policy={
            "requested_encoder": str(settings.render_video_encoder or "auto"),
            "hardware_smoke_probe": bool(
                settings.render_hardware_encoder_smoke_probe
            ),
            "hardware_fallback_enabled": bool(
                settings.render_hardware_encoder_fallback_enabled
            ),
            "geometry_transform": "none",
            "color_transform": "none",
            "invisible_perturbation": False,
        },
    )
    recipe_path = root / "phase4_render_recipe.json"
    _write_json_atomic(recipe_path, recipe)
    counts = dict(contract.get("counts") or {})
    qa_counts = dict(report.get("counts") or {})
    meta = {
        "schema_version": "phase4_preflight_meta_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": report.get("status"),
        "final_render_gate": final_render_gate,
        "phase3_render_handoff_sha256": dict(
            dict(contract.get("refs") or {}).get("phase3_render_handoff_ref") or {}
        ).get("sha256"),
        "counts": counts,
        "typography": qa_counts,
        "frame_count_reconciliation": report.get("frame_count_reconciliation"),
        "residual_cjk": report.get("residual_cjk_preflight"),
        "artifacts": {
            "render_input_preview": "phase4_render_input_preview.json",
            "render_input": (
                "phase4_render_input.json"
                if report.get("status") == "READY_FOR_PHASE4"
                else None
            ),
            "preflight_report": "PHASE4_PREFLIGHT_REPORT.md",
            "visual_audit": (
                "PHASE4_PREFLIGHT_VISUAL_AUDIT.md"
                if (root / "PHASE4_PREFLIGHT_VISUAL_AUDIT.md").is_file()
                else None
            ),
            "render_recipe": recipe_path.name,
            "pts_map": pts_map_path.name if pts_map_path is not None else None,
            "samples": [
                path.relative_to(root).as_posix() for path in samples if path.is_relative_to(root)
            ],
        },
    }
    _write_json_atomic(root / "phase4_preflight_meta.json", meta)
    logger.info(
        "phase4_preflight_completed status=%s render_tracks=%s overflow=%s clamp=%s collisions=%s samples=%s",
        report.get("status"),
        counts.get("render_tracks", 0),
        qa_counts.get("text_overflow", 0),
        qa_counts.get("clamp_required", 0),
        qa_counts.get("collision_events", 0),
        len(samples),
    )
    return 0 if report.get("status") == "READY_FOR_PHASE4" else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m scripts.run_phase4_preflight <phase3_output_dir>")
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args[0])
    except Phase4InputError as exc:
        print(f"[P4-PREFLIGHT][FAIL] {exc}", flush=True)
        return 1
    except Exception as exc:
        print(f"[P4-PREFLIGHT][FAIL] {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
