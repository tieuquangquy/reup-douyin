"""Lightweight local DBNet-style text detector via onnxruntime."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)


def resolve_dbnet_execution_providers(available: list[str]) -> list[str]:
    """Select an explicitly enabled accelerator, with deterministic CPU fallback."""

    requested = os.environ.get("DBNET_ONNX_PROVIDER", "cpu").strip().lower()
    aliases = {
        "cuda": "CUDAExecutionProvider",
        "directml": "DmlExecutionProvider",
        "dml": "DmlExecutionProvider",
        "cpu": "CPUExecutionProvider",
    }
    selected = aliases.get(requested, "CPUExecutionProvider")
    if selected not in available:
        logger.warning(
            "dbnet_execution_provider_unavailable requested=%s available=%s fallback=cpu",
            requested,
            available,
        )
        selected = "CPUExecutionProvider"
    providers = [selected]
    if selected != "CPUExecutionProvider" and "CPUExecutionProvider" in available:
        providers.append("CPUExecutionProvider")
    return providers

# Higher long-edge improves recall on 1080p; ONNX accepts dynamic H/W.
_DET_LONG_EDGE = 640
_BIN_THRESH = 0.3
_MIN_BOX_AREA_FRAC = 0.00015  # drop tiny noise blobs on full frame
_EXPAND_PAD_W_FRAC = 0.10
_EXPAND_PAD_H_TOP_FRAC = 0.40
_EXPAND_PAD_H_BOTTOM_FRAC = 0.25
_MERGE_Y_CENTER_FRAC = 0.55  # |cy1-cy2| <= this * max(h1,h2)
_MERGE_MAX_X_GAP_FRAC = 0.18  # title|body hardsub gaps on 1080p
# Approximate ImageNet mean/std in 0–1 space (BGR→RGB before apply).
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class TextBox:
    """Axis-aligned box in normalized xywh (0–1) on the original frame."""

    x: float
    y: float
    width: float
    height: float

    def as_xyxy(self) -> tuple[float, float, float, float]:
        return (
            float(self.x),
            float(self.y),
            float(self.x) + float(self.width),
            float(self.y) + float(self.height),
        )


def box_iou(a: TextBox, b: TextBox) -> float:
    """Intersection-over-union of two normalized boxes."""
    ax0, ay0, ax1, ay1 = a.as_xyxy()
    bx0, by0, bx1, by1 = b.as_xyxy()
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    if union <= 1e-12:
        return 0.0
    return float(inter / union)


def max_iou_against(box: TextBox, previous: list[TextBox]) -> float:
    if not previous:
        return 0.0
    return max(box_iou(box, prev) for prev in previous)


def has_new_text_boxes(
    current: list[TextBox],
    previous: list[TextBox],
    *,
    iou_new_thresh: float = 0.3,
) -> bool:
    """True when at least one current box is unmatched / low-IoU vs previous."""
    if not current:
        return False
    if not previous:
        return True
    for box in current:
        if max_iou_against(box, previous) < float(iou_new_thresh):
            return True
    return False


def preprocess_bgr_for_dbnet(
    frame_bgr: np.ndarray,
    *,
    long_edge: int = _DET_LONG_EDGE,
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """
    Resize (long edge), pad to multiple of 32, normalize RGB → NCHW float32.

    Returns ``(tensor[1,3,H,W], scale, (pad_h, pad_w))`` where ``scale`` maps
    original pixels → network canvas (before pad).
    """
    if frame_bgr is None or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Expected HxWx3 BGR frame, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    if h < 2 or w < 2:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Frame too small: {w}x{h}",
        )
    scale = float(long_edge) / float(max(h, w))
    new_w = max(32, int(round(w * scale)))
    new_h = max(32, int(round(h * scale)))
    # Pad to multiple of 32 (DBNet / FPN friendly).
    pad_w = int(np.ceil(new_w / 32.0) * 32)
    pad_h = int(np.ceil(new_h / 32.0) * 32)

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((pad_h, pad_w, 3), dtype=np.float32)
    canvas[:new_h, :new_w] = resized.astype(np.float32) / 255.0
    canvas = (canvas - _MEAN) / _STD
    nchw = np.transpose(canvas, (2, 0, 1))[None, ...].astype(np.float32)
    return nchw, scale, (pad_h, pad_w)


def postprocess_prob_map(
    prob_map: np.ndarray,
    *,
    orig_h: int,
    orig_w: int,
    scale: float,
    bin_thresh: float = _BIN_THRESH,
) -> list[TextBox]:
    """Binarize probability map → contours → normalized xywh on original frame."""
    arr = np.asarray(prob_map)
    if arr.ndim == 4:
        arr = arr[0, 0] if arr.shape[1] == 1 else arr[0]
    elif arr.ndim == 3:
        arr = arr[0] if arr.shape[0] == 1 else arr[:, :, 0]
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim != 2:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Unexpected DBNet output shape {getattr(prob_map, 'shape', None)}",
        )

    binary = (arr >= float(bin_thresh)).astype(np.uint8) * 255
    contours, _hierarchy = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_area = float(orig_h * orig_w) * _MIN_BOX_AREA_FRAC
    boxes: list[TextBox] = []
    inv = 1.0 / max(scale, 1e-6)
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        # Map from network canvas (pre-pad coords ≈ resized) back to original.
        ox0 = max(0.0, float(x) * inv)
        oy0 = max(0.0, float(y) * inv)
        ox1 = min(float(orig_w), float(x + bw) * inv)
        oy1 = min(float(orig_h), float(y + bh) * inv)
        ww, hh = ox1 - ox0, oy1 - oy0
        if ww * hh < min_area or ww < 2 or hh < 2:
            continue
        boxes.append(
            TextBox(
                x=ox0 / float(orig_w),
                y=oy0 / float(orig_h),
                width=ww / float(orig_w),
                height=hh / float(orig_h),
            )
        )
    return boxes


def expand_text_boxes(
    boxes: list[TextBox],
    *,
    pad_w_frac: float = _EXPAND_PAD_W_FRAC,
    pad_h_top_frac: float = _EXPAND_PAD_H_TOP_FRAC,
    pad_h_bottom_frac: float = _EXPAND_PAD_H_BOTTOM_FRAC,
    pad_h_frac: float | None = None,
) -> list[TextBox]:
    """Grow each normalized box (more pad on top) to cover truncated glyphs; clamp [0,1]."""
    pw = max(0.0, float(pad_w_frac))
    if pad_h_frac is not None:
        ph_top = ph_bot = max(0.0, float(pad_h_frac))
    else:
        ph_top = max(0.0, float(pad_h_top_frac))
        ph_bot = max(0.0, float(pad_h_bottom_frac))
    out: list[TextBox] = []
    for box in boxes:
        dx = float(box.width) * pw
        dy_top = float(box.height) * ph_top
        dy_bot = float(box.height) * ph_bot
        x0 = max(0.0, float(box.x) - dx)
        y0 = max(0.0, float(box.y) - dy_top)
        x1 = min(1.0, float(box.x) + float(box.width) + dx)
        y1 = min(1.0, float(box.y) + float(box.height) + dy_bot)
        ww = max(0.0, x1 - x0)
        hh = max(0.0, y1 - y0)
        if ww < 1e-6 or hh < 1e-6:
            continue
        out.append(TextBox(x=x0, y=y0, width=ww, height=hh))
    return out


def _boxes_same_text_line(a: TextBox, b: TextBox, *, max_x_gap: float) -> bool:
    ax0, ay0, ax1, ay1 = a.as_xyxy()
    bx0, by0, bx1, by1 = b.as_xyxy()
    ah = max(1e-6, ay1 - ay0)
    bh = max(1e-6, by1 - by0)
    acy = (ay0 + ay1) * 0.5
    bcy = (by0 + by1) * 0.5
    if abs(acy - bcy) > _MERGE_Y_CENTER_FRAC * max(ah, bh):
        return False
    # Vertical overlap of y-intervals helps reject stacked UI rows.
    y_overlap = max(0.0, min(ay1, by1) - max(ay0, by0))
    if y_overlap < 0.35 * min(ah, bh):
        return False
    if ax1 < bx0:
        gap = bx0 - ax1
    elif bx1 < ax0:
        gap = ax0 - bx1
    else:
        gap = 0.0
    return gap <= float(max_x_gap)


def merge_collinear_text_boxes(
    boxes: list[TextBox],
    *,
    max_x_gap_frac: float = _MERGE_MAX_X_GAP_FRAC,
) -> list[TextBox]:
    """Union adjacent same-baseline fragments into one line box."""
    if len(boxes) <= 1:
        return list(boxes)
    remaining = sorted(boxes, key=lambda b: (b.y + b.height * 0.5, b.x))
    merged: list[TextBox] = []
    while remaining:
        cur = remaining.pop(0)
        changed = True
        while changed:
            changed = False
            nxt: list[TextBox] = []
            for other in remaining:
                if _boxes_same_text_line(cur, other, max_x_gap=max_x_gap_frac):
                    x0 = min(cur.x, other.x)
                    y0 = min(cur.y, other.y)
                    x1 = max(cur.x + cur.width, other.x + other.width)
                    y1 = max(cur.y + cur.height, other.y + other.height)
                    cur = TextBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
                    changed = True
                else:
                    nxt.append(other)
            remaining = nxt
        merged.append(cur)
    return merged


class LocalTextDetector:
    """ONNX DBNet (det-only) for deciding whether a frame contains text glyphs."""

    def __init__(self, model_path: Path | str):
        path = Path(model_path)
        if not path.is_file():
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_MISSING,
                f"DBNet ONNX model missing: {path}",
            )
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_MISSING,
                "onnxruntime is required for text_onnx frame backend "
                "(pip install onnxruntime)",
            ) from exc
        try:
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            # This exported dynamic-shape DBNet carries a stale 320x320 output
            # annotation. ORT otherwise emits one VerifyOutputSizes warning per
            # frame even though the dynamic output is valid, flooding long-video
            # logs and hiding the actionable terminal exception.
            opts.log_severity_level = 3  # errors only; inference failures still raise
            providers = resolve_dbnet_execution_providers(list(ort.get_available_providers()))
            self._session = ort.InferenceSession(
                str(path),
                sess_options=opts,
                providers=providers,
            )
            self._input_name = self._session.get_inputs()[0].name
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_LOAD_FAILED,
                f"Failed to load DBNet ONNX ({path.name}): {exc}",
            ) from exc
        self.model_path = path
        logger.info(
            "local_text_detector_ready model=%s providers=%s",
            path.name,
            self._session.get_providers(),
        )

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        long_edge: int = _DET_LONG_EDGE,
        bin_thresh: float = _BIN_THRESH,
        rematch_after_expand: bool = False,
        expand_pad_w_frac: float | None = None,
        expand_pad_h_top_frac: float | None = None,
        expand_pad_h_bottom_frac: float | None = None,
    ) -> list[TextBox]:
        """Return normalized text boxes for one BGR frame."""
        h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
        tensor, scale, _pad = preprocess_bgr_for_dbnet(
            frame_bgr,
            long_edge=max(_DET_LONG_EDGE, int(long_edge)),
        )
        try:
            outputs = self._session.run(None, {self._input_name: tensor})
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_INFER_FAILED,
                f"DBNet inference failed: {exc}",
            ) from exc
        if not outputs:
            return []
        boxes = postprocess_prob_map(
            outputs[0],
            orig_h=h,
            orig_w=w,
            scale=scale,
            bin_thresh=float(bin_thresh),
        )
        boxes = merge_collinear_text_boxes(boxes)
        boxes = expand_text_boxes(
            boxes,
            pad_w_frac=(
                float(expand_pad_w_frac)
                if expand_pad_w_frac is not None
                else _EXPAND_PAD_W_FRAC
            ),
            pad_h_top_frac=(
                float(expand_pad_h_top_frac)
                if expand_pad_h_top_frac is not None
                else _EXPAND_PAD_H_TOP_FRAC
            ),
            pad_h_bottom_frac=(
                float(expand_pad_h_bottom_frac)
                if expand_pad_h_bottom_frac is not None
                else _EXPAND_PAD_H_BOTTOM_FRAC
            ),
        )
        if rematch_after_expand and len(boxes) > 1:
            # Expand can close title|body gaps that pre-expand merge missed.
            boxes = merge_collinear_text_boxes(boxes)
        return boxes
