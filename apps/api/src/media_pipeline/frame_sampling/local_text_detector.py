"""Lightweight local DBNet-style text detector via onnxruntime."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)

# chineseocr_lite dbnet.onnx expects long-edge ~320 (ImageNet-ish normalize).
_DET_LONG_EDGE = 320
_BIN_THRESH = 0.3
_MIN_BOX_AREA_FRAC = 0.00015  # drop tiny noise blobs on full frame
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
            self._session = ort.InferenceSession(
                str(path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_LOAD_FAILED,
                f"Failed to load DBNet ONNX ({path.name}): {exc}",
            ) from exc
        self.model_path = path
        logger.info("local_text_detector_ready model=%s", path.name)

    def detect(self, frame_bgr: np.ndarray) -> list[TextBox]:
        """Return normalized text boxes for one BGR frame."""
        h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
        tensor, scale, _pad = preprocess_bgr_for_dbnet(frame_bgr)
        try:
            outputs = self._session.run(None, {self._input_name: tensor})
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_INFER_FAILED,
                f"DBNet inference failed: {exc}",
            ) from exc
        if not outputs:
            return []
        return postprocess_prob_map(outputs[0], orig_h=h, orig_w=w, scale=scale)
