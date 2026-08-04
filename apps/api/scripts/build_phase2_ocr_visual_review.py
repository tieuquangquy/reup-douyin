"""Build hash-bound visual contact sheets for exact Phase 2 OCR review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np


class Phase2OcrVisualReviewError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2OcrVisualReviewError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase2OcrVisualReviewError(f"{path.name} must contain an object")
    return payload


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


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _fit(image: np.ndarray, *, width: int, height: int) -> np.ndarray:
    canvas = np.full((height, width, 3), 24, dtype=np.uint8)
    if image is None or image.size == 0:
        return canvas
    source_h, source_w = image.shape[:2]
    scale = min(width / max(1, source_w), height / max(1, source_h))
    resized = cv2.resize(
        image,
        (
            max(1, int(round(source_w * scale))),
            max(1, int(round(source_h * scale))),
        ),
        interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC,
    )
    y0 = (height - resized.shape[0]) // 2
    x0 = (width - resized.shape[1]) // 2
    canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
    return canvas


def _asset_paths(root: Path, content: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for raw in list(content.get("review_assets") or []):
        if not isinstance(raw, Mapping):
            continue
        for key in ("crop_path", "best_keyframe_path"):
            value = str(raw.get(key) or "").strip()
            if not value:
                continue
            path = (root / value).resolve()
            if path.is_relative_to(root) and path.is_file() and path not in paths:
                paths.append(path)
                break
        if len(paths) >= 2:
            break
    return paths


def build_visual_review(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    queue_path = root / "phase2_review_queue.json"
    proposal_path = root / "phase2_review_proposal.json"
    queue = _load_object(queue_path)
    proposal = _load_object(proposal_path)
    unsigned_proposal = dict(proposal)
    claimed_proposal = str(unsigned_proposal.pop("proposal_sha256", "") or "")
    if len(claimed_proposal) != 64 or claimed_proposal != _sha256_json(
        unsigned_proposal
    ):
        raise Phase2OcrVisualReviewError("Phase 2 proposal self-hash is invalid")
    if str(dict(proposal.get("review_queue_ref") or {}).get("sha256") or "") != (
        _sha256_file(queue_path)
    ):
        raise Phase2OcrVisualReviewError("Phase 2 proposal is stale")
    proposal_by_id = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(proposal.get("proposals") or [])
        if isinstance(row, Mapping)
    }
    objects = [
        dict(row)
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping)
    ]
    if set(proposal_by_id) != {
        str(row.get("content_id") or "") for row in objects
    }:
        raise Phase2OcrVisualReviewError("Proposal does not cover the OCR queue")
    def _priority(content: Mapping[str, Any]) -> tuple[str, tuple[int, str]]:
        content_id = str(content.get("content_id") or "")
        proposal_row = proposal_by_id[content_id]
        status = str(proposal_row.get("proposal_status") or "")
        decision = str(proposal_row.get("proposed_decision") or "")
        candidate = str(content.get("ocr_text_candidate") or "").strip()
        if status == "OPERATOR_INPUT_REQUIRED":
            return "P0_INPUT_REQUIRED", (0, content_id)
        if decision == "REJECT_UI":
            return "P0_REJECT_UI", (1, content_id)
        if decision == "EDIT":
            return "P1_EDIT", (2, content_id)
        if not candidate:
            return "P1_EMPTY", (3, content_id)
        return "P2_EXACT_CONFIRM", (4, content_id)

    objects.sort(key=lambda row: _priority(row)[1])

    output_dir = root / "qa" / "phase2_ocr_review_sheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    columns, rows_per_sheet = 3, 4
    tile_w, tile_h, header_h = 440, 240, 32
    per_sheet = columns * rows_per_sheet
    index_rows: list[dict[str, Any]] = []
    sheet_refs: list[dict[str, Any]] = []
    for sheet_index, offset in enumerate(range(0, len(objects), per_sheet), 1):
        batch = objects[offset : offset + per_sheet]
        sheet = np.full(
            (rows_per_sheet * tile_h, columns * tile_w, 3), 12, dtype=np.uint8
        )
        for tile_index, content in enumerate(batch):
            row_index, column_index = divmod(tile_index, columns)
            x0, y0 = column_index * tile_w, row_index * tile_h
            candidate = str(content.get("ocr_text_candidate") or "").strip()
            priority, _ = _priority(content)
            color = (
                (40, 40, 220)
                if priority.startswith("P0")
                else (30, 150, 230)
                if priority == "P1_EDIT"
                else (40, 180, 40)
            )
            cv2.rectangle(sheet, (x0, y0), (x0 + tile_w - 1, y0 + tile_h - 1), color, 2)
            cv2.rectangle(sheet, (x0, y0), (x0 + tile_w, y0 + header_h), (0, 0, 0), -1)
            label = f"{content.get('content_id')}  {priority}"
            cv2.putText(
                sheet,
                label,
                (x0 + 8, y0 + 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                1,
                cv2.LINE_AA,
            )
            assets = _asset_paths(root, content)
            body_y = y0 + header_h
            body_h = tile_h - header_h
            if not assets:
                cv2.putText(
                    sheet,
                    "NO VISUAL ASSET",
                    (x0 + 90, body_y + body_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
            else:
                panel_w = tile_w // len(assets)
                for asset_index, asset in enumerate(assets):
                    image = cv2.imread(str(asset))
                    panel = _fit(image, width=panel_w, height=body_h)
                    px = x0 + asset_index * panel_w
                    sheet[body_y : body_y + body_h, px : px + panel_w] = panel
            proposal_row = proposal_by_id[str(content.get("content_id") or "")]
            index_rows.append(
                {
                    "content_id": content.get("content_id"),
                    "priority": priority,
                    "sheet": f"qa/phase2_ocr_review_sheets/sheet_{sheet_index:03d}.jpg",
                    "tile_index": tile_index + 1,
                    "ocr_text_candidate": candidate or None,
                    "ocr_text_suggested": proposal_row.get("ocr_text_suggested"),
                    "proposed_decision": proposal_row.get("proposed_decision"),
                    "proposal_status": proposal_row.get("proposal_status"),
                    "recommendation_reason": proposal_row.get(
                        "recommendation_reason"
                    ),
                    "roles": list(content.get("roles") or []),
                    "geometry_refs": list(content.get("geometry_refs") or []),
                    "review_input_sha256": content.get("review_input_sha256"),
                    "assets": [
                        {
                            "path": asset.relative_to(root).as_posix(),
                            "sha256": _sha256_file(asset),
                        }
                        for asset in assets
                    ],
                }
            )
        sheet_path = output_dir / f"sheet_{sheet_index:03d}.jpg"
        if not cv2.imwrite(
            str(sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92]
        ):
            raise Phase2OcrVisualReviewError("Cannot write OCR review sheet")
        sheet_refs.append(
            {
                "path": sheet_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(sheet_path),
                "objects": len(batch),
            }
        )

    artifact: dict[str, Any] = {
        "schema_version": "phase2_ocr_visual_review_v1",
        "status": "EXACT_OCR_OPERATOR_REVIEW_REQUIRED",
        "review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "proposal_ref": {
            "path": proposal_path.name,
            "sha256": _sha256_file(proposal_path),
            "proposal_sha256": proposal.get("proposal_sha256"),
        },
        "counts": {
            "objects": len(index_rows),
            "empty_candidates": sum(
                not str(row.get("ocr_text_candidate") or "").strip()
                for row in index_rows
            ),
            "exact_confirmation": sum(
                row["priority"] == "P2_EXACT_CONFIRM" for row in index_rows
            ),
            "proposed_edits": sum(
                row["priority"] == "P1_EDIT" for row in index_rows
            ),
            "proposed_reject_ui": sum(
                row["priority"] == "P0_REJECT_UI" for row in index_rows
            ),
            "operator_input_required": sum(
                row["priority"] == "P0_INPUT_REQUIRED" for row in index_rows
            ),
            "sheets": len(sheet_refs),
        },
        "sheets": sheet_refs,
        "objects": index_rows,
        "operator_decision": None,
    }
    artifact["visual_review_sha256"] = _sha256_json(artifact)
    _write_json_atomic(root / "phase2_ocr_visual_review.json", artifact)

    lines = [
        "# Phase 2 exact OCR visual review",
        "",
        f"- Objects: `{artifact['counts']['objects']}`",
        f"- Empty candidates (review first): `{artifact['counts']['empty_candidates']}`",
        f"- Non-empty exact confirmations: `{artifact['counts']['exact_confirmation']}`",
        f"- Proposed edits: `{artifact['counts']['proposed_edits']}`",
        f"- Proposed REJECT_UI: `{artifact['counts']['proposed_reject_ui']}`",
        f"- Operator input required: `{artifact['counts']['operator_input_required']}`",
        f"- Visual review SHA-256: `{artifact['visual_review_sha256']}`",
        "",
        "Contact sheets are navigation aids only. Confirm text from the linked crop/keyframe before approving.",
        "",
        "| Priority | Object | Candidate | Proposed | Decision | Reason | Geometry | Sheet |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in index_rows:
        candidate = json.dumps(
            str(row.get("ocr_text_candidate") or ""), ensure_ascii=False
        ).replace("|", "\\|")
        suggested = json.dumps(
            str(row.get("ocr_text_suggested") or ""), ensure_ascii=False
        ).replace("|", "\\|")
        reason = json.dumps(
            str(row.get("recommendation_reason") or ""), ensure_ascii=False
        ).replace("|", "\\|")
        lines.append(
            f"| `{row['priority']}` | `{row['content_id']}` | `{candidate}` | "
            f"`{suggested}` | `{row.get('proposed_decision') or ''}` | `{reason}` | "
            f"`{', '.join(row['geometry_refs'])}` | "
            f"[sheet {row['tile_index']}]({row['sheet']}) |"
        )
    _write_text_atomic(
        root / "PHASE2_OCR_VISUAL_REVIEW.md", "\n".join(lines) + "\n"
    )
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args()
    result = build_visual_review(args.root)
    print(
        json.dumps(
            {
                "status": result["status"],
                "counts": result["counts"],
                "visual_review_sha256": result["visual_review_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
