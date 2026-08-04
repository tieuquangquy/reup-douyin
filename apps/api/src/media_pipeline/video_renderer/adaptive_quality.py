"""Mask confidence, damage budgets, and temporal background stabilization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


def _gray_values(image: np.ndarray, selector: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        return np.asarray([], dtype=np.float64)
    bgr = image.astype(np.float64)
    gray = 0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
    return gray[selector]


def _ssim_values(before: np.ndarray, after: np.ndarray) -> float:
    if before.size < 2 or after.size != before.size:
        return 1.0
    x = before.astype(np.float64)
    y = after.astype(np.float64)
    mean_x = float(x.mean())
    mean_y = float(y.mean())
    var_x = float(x.var())
    var_y = float(y.var())
    covariance = float(((x - mean_x) * (y - mean_y)).mean())
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    numerator = (2 * mean_x * mean_y + c1) * (2 * covariance + c2)
    denominator = (mean_x**2 + mean_y**2 + c1) * (var_x + var_y + c2)
    if denominator <= 1e-9:
        return 1.0
    return max(-1.0, min(1.0, numerator / denominator))


def assess_mask_quality(
    mask: np.ndarray,
    *,
    cover_roi_px: tuple[int, int, int, int],
    max_frame_change_fraction: float,
    allow_dense_roi: bool = False,
    max_roi_fill_fraction: float = 0.80,
) -> dict[str, Any]:
    if mask.ndim != 2 or mask.size == 0:
        return {
            "status": "BLOCKED",
            "blocked_reasons": ["mask_invalid"],
            "metrics": {},
        }
    height, width = mask.shape[:2]
    x0, y0, x1, y1 = (int(value) for value in cover_roi_px)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    selected = mask > 0
    count = int(np.count_nonzero(selected))
    frame_fraction = count / float(mask.size)
    roi = np.zeros_like(selected)
    if x1 > x0 and y1 > y0:
        roi[y0:y1, x0:x1] = True
    roi_area = int(np.count_nonzero(roi))
    inside = int(np.count_nonzero(selected & roi))
    outside = int(np.count_nonzero(selected & (~roi)))
    roi_fill_fraction = inside / float(max(1, roi_area))
    spill_fraction = outside / float(max(1, count))
    blocked: list[str] = []
    if count == 0:
        blocked.append("mask_empty")
    if frame_fraction > float(max_frame_change_fraction):
        blocked.append("mask_frame_fraction")
    if spill_fraction > 0.05:
        blocked.append("mask_outside_cover_roi")
    roi_fill_limit = (
        1.0
        if allow_dense_roi
        else max(0.0, min(1.0, float(max_roi_fill_fraction)))
    )
    if count and roi_fill_fraction > roi_fill_limit:
        blocked.append("mask_too_dense_for_ink")
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "blocked_reasons": blocked,
        "metrics": {
            "mask_pixels": count,
            "frame_fraction": round(frame_fraction, 6),
            "roi_fill_fraction": round(roi_fill_fraction, 6),
            "max_roi_fill_fraction": round(roi_fill_limit, 6),
            "spill_fraction": round(spill_fraction, 6),
        },
    }


def evaluate_damage_budget(
    before: np.ndarray,
    after: np.ndarray,
    mask: np.ndarray,
    budget: Mapping[str, Any],
    frame_pixel_count: int | None = None,
) -> dict[str, Any]:
    if before.shape != after.shape or before.ndim != 3 or mask.shape != before.shape[:2]:
        return {
            "status": "BLOCKED",
            "blocked_reasons": ["damage_inputs_invalid"],
            "metrics": {},
        }
    delta = np.abs(after.astype(np.float32) - before.astype(np.float32))
    changed = np.max(delta, axis=2) > 2.0
    changed_fraction = float(np.count_nonzero(changed)) / float(
        max(1, int(frame_pixel_count or changed.size))
    )
    outside = mask <= 0
    outside_mad = float(delta[outside].mean()) if np.any(outside) else 0.0
    outside_before = _gray_values(before, outside)
    outside_after = _gray_values(after, outside)
    outside_ssim = _ssim_values(outside_before, outside_after)
    blocked: list[str] = []
    if changed_fraction > float(budget.get("max_frame_change_fraction") or 0.0):
        blocked.append("frame_damage_fraction")
    if outside_mad > float(budget.get("max_outside_mask_mean_abs_delta") or 0.0):
        blocked.append("outside_mask_damage")
    if outside_ssim < float(budget.get("min_outside_mask_ssim") or 0.0):
        if "outside_mask_damage" not in blocked:
            blocked.append("outside_mask_damage")
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "blocked_reasons": blocked,
        "metrics": {
            "changed_fraction": round(changed_fraction, 6),
            "outside_mask_mean_abs_delta": round(outside_mad, 4),
            "outside_mask_ssim": round(outside_ssim, 6),
        },
    }


@dataclass
class _TemporalEntry:
    source: np.ndarray
    cleaned: np.ndarray
    mask: np.ndarray
    seeded: bool = False


class TemporalInpaintState:
    """Reuse or motion-warp a clean plate; fall back to spatial Telea safely."""

    def __init__(self) -> None:
        self._entries: dict[str, _TemporalEntry] = {}

    def seed(self, key: str, clean_reference_bgr: np.ndarray) -> None:
        if clean_reference_bgr.ndim != 3 or clean_reference_bgr.shape[2] != 3:
            raise ValueError("Temporal reference must be HxWx3 BGR")
        empty_mask = np.zeros(clean_reference_bgr.shape[:2], dtype=np.uint8)
        self._entries[str(key)] = _TemporalEntry(
            source=clean_reference_bgr.copy(),
            cleaned=clean_reference_bgr.copy(),
            mask=empty_mask,
            seeded=True,
        )

    @staticmethod
    def _spatial(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
        import cv2

        return cv2.inpaint(frame.copy(), mask.astype(np.uint8), 3, cv2.INPAINT_TELEA)

    def clean(
        self, frame_bgr: np.ndarray, mask: np.ndarray, *, key: str
    ) -> tuple[np.ndarray, dict[str, Any]]:
        import cv2

        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or mask.shape != frame_bgr.shape[:2]:
            raise ValueError("Temporal inpaint frame/mask shape mismatch")
        binary = np.where(mask > 0, 255, 0).astype(np.uint8)
        spatial = self._spatial(frame_bgr, binary)
        previous = self._entries.get(str(key))
        if previous is None or previous.source.shape != frame_bgr.shape:
            self._entries[str(key)] = _TemporalEntry(
                source=frame_bgr.copy(), cleaned=spatial.copy(), mask=binary.copy()
            )
            return spatial, {"mode": "spatial_bootstrap", "motion_mad": None}

        comparison = (binary <= 0) & (previous.mask <= 0)
        motion_mad = (
            float(
                np.abs(
                    frame_bgr[comparison].astype(np.float32)
                    - previous.source[comparison].astype(np.float32)
                ).mean()
            )
            if np.any(comparison)
            else 255.0
        )
        if motion_mad <= 1.0:
            output = spatial.copy()
            output[binary > 0] = previous.cleaned[binary > 0]
            mode = "static_plate"
        else:
            prev_gray = cv2.cvtColor(previous.source, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            height, width = curr_gray.shape
            warped_source: np.ndarray | None = None
            warped_cleaned: np.ndarray | None = None
            reference_mode = ""
            if previous.seeded:
                warp = np.eye(2, 3, dtype=np.float32)
                criteria = (
                    cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                    80,
                    1e-5,
                )
                try:
                    cv2.findTransformECC(
                        curr_gray,
                        prev_gray,
                        warp,
                        cv2.MOTION_AFFINE,
                        criteria,
                        inputMask=(comparison.astype(np.uint8) * 255),
                        gaussFiltSize=5,
                    )
                    warped_source = cv2.warpAffine(
                        previous.source,
                        warp,
                        (width, height),
                        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                        borderMode=cv2.BORDER_REFLECT,
                    )
                    warped_cleaned = cv2.warpAffine(
                        previous.cleaned,
                        warp,
                        (width, height),
                        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                        borderMode=cv2.BORDER_REFLECT,
                    )
                    reference_mode = "affine_reference_plate"
                except cv2.error:
                    warped_source = None
                    warped_cleaned = None
            if warped_source is None or warped_cleaned is None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray,
                    curr_gray,
                    None,
                    0.5,
                    3,
                    15,
                    3,
                    5,
                    1.2,
                    0,
                )
                grid_x, grid_y = np.meshgrid(
                    np.arange(width, dtype=np.float32),
                    np.arange(height, dtype=np.float32),
                )
                warped_source = cv2.remap(
                    previous.source,
                    grid_x - flow[:, :, 0],
                    grid_y - flow[:, :, 1],
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REFLECT,
                )
                warped_cleaned = cv2.remap(
                    previous.cleaned,
                    grid_x - flow[:, :, 0],
                    grid_y - flow[:, :, 1],
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REFLECT,
                )
                reference_mode = (
                    "flow_reference_plate" if previous.seeded else "flow_plate"
                )
            residual = (
                float(
                    np.abs(
                        warped_source[comparison].astype(np.float32)
                        - frame_bgr[comparison].astype(np.float32)
                    ).mean()
                )
                if np.any(comparison)
                else 255.0
            )
            threshold = 18.0 if previous.seeded else 12.0
            if residual <= threshold:
                output = spatial.copy()
                if previous.seeded:
                    output[binary > 0] = warped_cleaned[binary > 0]
                    mode = reference_mode
                else:
                    blended = (
                        0.70 * warped_cleaned.astype(np.float32)
                        + 0.30 * spatial.astype(np.float32)
                    ).astype(np.uint8)
                    output[binary > 0] = blended[binary > 0]
                    mode = "flow_plate"
            else:
                output = spatial
                mode = "spatial_fallback"

        self._entries[str(key)] = _TemporalEntry(
            source=frame_bgr.copy(), cleaned=output.copy(), mask=binary.copy()
        )
        return output, {"mode": mode, "motion_mad": round(motion_mad, 4)}
