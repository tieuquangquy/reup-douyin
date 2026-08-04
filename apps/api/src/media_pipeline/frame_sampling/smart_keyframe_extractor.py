"""Smart keyframe extraction: blur filter, DBNet text detect, centroid track, enhance."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.spatial.distance import cdist

from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx
from src.media_pipeline.frame_sampling.ensure_fsrcnn_model import ensure_fsrcnn_pb
from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector, TextBox

logger = logging.getLogger(__name__)

_UPSCALE_FACTOR = 1.5


def _print_info(message: str) -> None:
    """Terminal log (Prompt 1); safe on Windows cp1252 consoles."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"), flush=True)


@dataclass(frozen=True)
class BoundingBoxXYXY:
    """Pixel-space axis-aligned box (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) * 0.5, (self.y0 + self.y1) * 0.5)

    def clamp(self, width: int, height: int) -> BoundingBoxXYXY:
        return BoundingBoxXYXY(
            x0=float(max(0, min(width - 1, int(round(self.x0))))),
            y0=float(max(0, min(height - 1, int(round(self.y0))))),
            x1=float(max(0, min(width, int(round(self.x1))))),
            y1=float(max(0, min(height, int(round(self.y1))))),
        )


@dataclass
class KeyframeResult:
    frame_index: int
    frame_bgr: np.ndarray
    boxes: list[BoundingBoxXYXY]
    centroids: np.ndarray
    enhanced_crops: list[np.ndarray] = field(default_factory=list)


def centroids_from_boxes(boxes: list[BoundingBoxXYXY]) -> np.ndarray:
    """Return (N, 2) float64 centroids for the given boxes."""
    if not boxes:
        return np.zeros((0, 2), dtype=np.float64)
    return np.asarray([b.centroid for b in boxes], dtype=np.float64)


def has_new_centroid(
    current: np.ndarray,
    previous: np.ndarray,
    *,
    threshold_px: float = 50.0,
) -> bool:
    """True when at least one current centroid is farther than threshold from all previous."""
    curr = np.asarray(current, dtype=np.float64).reshape(-1, 2)
    prev = np.asarray(previous, dtype=np.float64).reshape(-1, 2)
    if curr.size == 0:
        return False
    if prev.size == 0:
        return True
    dists = cdist(curr, prev, metric="euclidean")
    min_d = dists.min(axis=1)
    return bool(np.any(min_d > float(threshold_px)))


def text_boxes_to_xyxy(boxes: list[TextBox], width: int, height: int) -> list[BoundingBoxXYXY]:
    out: list[BoundingBoxXYXY] = []
    for b in boxes:
        x0, y0, x1, y1 = b.as_xyxy()
        out.append(
            BoundingBoxXYXY(
                x0=x0 * float(width),
                y0=y0 * float(height),
                x1=x1 * float(width),
                y1=y1 * float(height),
            )
        )
    return out


# Douyin chrome + geometry + zone taxonomy (after DBNet, before crop/OCR).
# Aligns with overlay_zones / subtitle_band: hardsub + mid-title + UI burn-in.
_CHROME_Y_MIN_FRAC = 0.08
_CHROME_Y_MAX_FRAC = 0.92
_CHROME_X_MAX_FRAC = 0.88
_CHROME_X_MAX_FRAC_DENSE = 0.97  # full-card UI calories near right edge
_MIN_ASPECT_W_OVER_H = 1.6
_MIN_ASPECT_W_OVER_H_DENSE = 0.70  # single CJK chars on nutrition cards
_MAX_TALL_ASPECT = 1.5  # drop if height > width * this
_HARDSUB_Y_MIN_FRAC = 2.0 / 3.0  # bottom third (subtitle_band)
_MID_TITLE_Y_MIN = 0.22
_MID_TITLE_Y_MAX = 0.65
_MID_TITLE_MIN_HEIGHT = 0.035
_MID_TITLE_MIN_WIDTH = 0.15  # require width — no tall-blob alt (rice FP)
_MID_TITLE_CX_MIN = 0.12
_MID_TITLE_CX_MAX = 0.88
_UI_LABEL_MIN_WIDTH_FRAC = 0.04
_UI_LABEL_MIN_WIDTH_FRAC_DENSE = 0.03
_DENSE_MIN_BOXES = 8
_DENSE_MIN_Y_SPAN = 0.35
_MIN_EDGE_DENSITY = 0.10  # fallback for light UI text (gray on white)
_MIN_GRAY_STD = 15.0
_MIN_GRAY_RANGE = 40
_PHOTO_SAT_MEAN_MIN = 40.0
_PHOTO_AXIS_DIAG_MAX = 1.15  # isotropic food thumbs; colored hardsub stays above


def _axis_vs_diagonal_edge_ratio(gray: np.ndarray) -> float:
    """Axis-aligned vs diagonal Sobel energy (text >> photo texture)."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag2 = gx * gx + gy * gy
    mask = mag2 > 30.0
    if not bool(np.any(mask)):
        return 0.0
    ang = np.abs(np.arctan2(gy, gx))
    bins = np.histogram(ang[mask], bins=[0.0, 0.4, 1.2, 1.8, 2.6, 3.15])[0]
    axis = float(bins[0] + bins[2] + bins[4])
    diag = float(bins[1] + bins[3])
    return axis / (diag + 1e-6)


def _looks_like_photo_region(crop_bgr: np.ndarray) -> bool:
    """True for saturated isotropic patches (food thumbnails), not colored hardsub."""
    if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.ndim != 3:
        return False
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    sat_mean = float(hsv[:, :, 1].mean())
    if sat_mean < _PHOTO_SAT_MEAN_MIN:
        return False
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    return _axis_vs_diagonal_edge_ratio(gray) < _PHOTO_AXIS_DIAG_MAX


def looks_like_text_region(frame_bgr: np.ndarray, box: BoundingBoxXYXY) -> bool:
    """
    Reject texture FPs (rice/salt/food thumbs) while keeping hardsub + light UI labels.

    Photo gate: high saturation + isotropic edges (food icons).
    Primary: sparse low-chroma ink (``_crop_has_ink_evidence``).
    Fallback: enough Canny edges + gray contrast (calorie numbers on white cards).
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return True
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(round(box.x0))))
    y0 = max(0, min(h - 1, int(round(box.y0))))
    x1 = max(x0 + 1, min(w, int(round(box.x1))))
    y1 = max(y0 + 1, min(h, int(round(box.y1))))
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    if _looks_like_photo_region(crop):
        return False
    from src.media_pipeline.frame_sampling.local_text_verifier import _crop_has_ink_evidence

    if _crop_has_ink_evidence(crop):
        return True
    if crop.ndim == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop
    edge_frac = float(cv2.Canny(gray, 60, 140).mean()) / 255.0
    if edge_frac < _MIN_EDGE_DENSITY:
        return False
    if float(gray.std()) < _MIN_GRAY_STD:
        return False
    if int(gray.max()) - int(gray.min()) < _MIN_GRAY_RANGE:
        return False
    return True


def box_edge_density(frame_bgr: np.ndarray, box: BoundingBoxXYXY) -> float:
    """Mean Canny edge fraction in box (diagnostics / tests)."""
    if frame_bgr is None or frame_bgr.size == 0:
        return 0.0
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(round(box.x0))))
    y0 = max(0, min(h - 1, int(round(box.y0))))
    x1 = max(x0 + 1, min(w, int(round(box.x1))))
    y1 = max(y0 + 1, min(h, int(round(box.y1))))
    roi = frame_bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    if roi.ndim == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi
    return float(cv2.Canny(gray, 60, 140).mean()) / 255.0


def _geometry_candidate(
    box: BoundingBoxXYXY,
    *,
    w: int,
    h: int,
    min_h_px: float,
    min_w_px: float,
) -> bool:
    bw = float(box.x1) - float(box.x0)
    bh = float(box.y1) - float(box.y0)
    if bw <= 0.0 or bh <= 0.0:
        return False
    if bh < min_h_px or bw < min_w_px:
        return False
    if bh > bw * _MAX_TALL_ASPECT:
        return False
    if bw / bh < _MIN_ASPECT_W_OVER_H:
        return False
    cy_n = ((box.y0 + box.y1) * 0.5) / float(h)
    if cy_n <= _CHROME_Y_MIN_FRAC or cy_n >= _CHROME_Y_MAX_FRAC:
        return False
    return True


def is_dense_burnin_layout(
    boxes: list[BoundingBoxXYXY],
    frame_width: int,
    frame_height: int,
) -> bool:
    """True when many horizontal labels span the frame (nutrition/endcard UI)."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    min_h_px = max(15.0, 0.012 * float(h))
    min_w_px = max(20.0, 0.025 * float(w))
    cands = [
        b
        for b in boxes
        if _geometry_candidate(b, w=w, h=h, min_h_px=min_h_px, min_w_px=min_w_px)
    ]
    if len(cands) < _DENSE_MIN_BOXES:
        return False
    ys = [(b.y0 + b.y1) * 0.5 / float(h) for b in cands]
    return (max(ys) - min(ys)) >= _DENSE_MIN_Y_SPAN


def filter_valid_text_boxes(
    boxes: list[BoundingBoxXYXY],
    frame_width: int,
    frame_height: int,
    frame_bgr: np.ndarray | None = None,
) -> list[BoundingBoxXYXY]:
    """
    Keep burn-in text for any Douyin layout; drop chrome + texture FPs.

    1. Chrome: status/music; right rail (relaxed on dense full-card UI).
    2. Geometry: min size, horizontal aspect.
    3. Zone OR: hardsub | mid_title (wide) | content_ui_label.
    4. Optional edge gate when ``frame_bgr`` is provided (kills rice/salt texture).
    """
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    dense = is_dense_burnin_layout(boxes, w, h)
    chrome_x_max = _CHROME_X_MAX_FRAC_DENSE if dense else _CHROME_X_MAX_FRAC
    ui_w_frac = _UI_LABEL_MIN_WIDTH_FRAC_DENSE if dense else _UI_LABEL_MIN_WIDTH_FRAC
    min_h_px = max(15.0, 0.012 * float(h))
    min_w_px = max(20.0, 0.025 * float(w)) if dense else max(24.0, 0.035 * float(w))
    min_aspect = _MIN_ASPECT_W_OVER_H_DENSE if dense else _MIN_ASPECT_W_OVER_H
    ui_min_w_px = float(ui_w_frac) * float(w)

    kept: list[BoundingBoxXYXY] = []
    for box in boxes:
        cx, cy = box.centroid
        cx_n = cx / float(w)
        cy_n = cy / float(h)
        bw = float(box.x1) - float(box.x0)
        bh = float(box.y1) - float(box.y0)
        if bw <= 0.0 or bh <= 0.0:
            continue

        if cy_n <= _CHROME_Y_MIN_FRAC or cy_n >= _CHROME_Y_MAX_FRAC:
            continue
        if cx_n >= chrome_x_max:
            continue

        if bh < min_h_px or bw < min_w_px:
            continue
        if bh > bw * _MAX_TALL_ASPECT:
            continue
        aspect = bw / bh
        if aspect < min_aspect:
            continue

        bw_n = bw / float(w)
        bh_n = bh / float(h)

        is_hardsub = cy_n >= _HARDSUB_Y_MIN_FRAC
        is_mid_title = (
            _MID_TITLE_Y_MIN <= cy_n <= _MID_TITLE_Y_MAX
            and bh_n >= _MID_TITLE_MIN_HEIGHT
            and bw_n >= _MID_TITLE_MIN_WIDTH
            and _MID_TITLE_CX_MIN <= cx_n <= _MID_TITLE_CX_MAX
        )
        is_ui_label = bw >= ui_min_w_px
        if not (is_hardsub or is_mid_title or is_ui_label):
            continue

        if frame_bgr is not None and not looks_like_text_region(frame_bgr, box):
            continue
        kept.append(box)
    return kept


class SmartKeyframeExtractor:
    """Sample video, skip blur, detect text via DBNet, track centroids, enhance crops."""

    def __init__(
        self,
        dbnet_model_path: Path | str | None = None,
        *,
        sample_stride: int = 5,
        blur_threshold: float = 100.0,
        centroid_new_px: float = 50.0,
        fade_in_wait_frames: int = 2,
        fsrcnn_model_path: Path | str | None = None,
        _skip_detector_init: bool = False,
    ) -> None:
        self.sample_stride = max(1, int(sample_stride))
        self.blur_threshold = float(blur_threshold)
        self.centroid_new_px = float(centroid_new_px)
        self.fade_in_wait_frames = max(0, int(fade_in_wait_frames))
        self._detector: LocalTextDetector | None = None
        self._previous_centroids = np.zeros((0, 2), dtype=np.float64)
        self._pending_boxes: list[BoundingBoxXYXY] | None = None
        self._pending_wait_left = 0
        self._fsrcnn_sr: Any | None = None
        self._fsrcnn_ready = False

        if fsrcnn_model_path is not None:
            self.fsrcnn_model_path: Path | None = Path(fsrcnn_model_path)
        elif not _skip_detector_init:
            try:
                self.fsrcnn_model_path = ensure_fsrcnn_pb()
            except Exception as exc:  # noqa: BLE001
                logger.info("fsrcnn_pb_ensure_failed err=%s; CPU Bicubic fallback", exc)
                self.fsrcnn_model_path = None
        else:
            self.fsrcnn_model_path = None

        if not _skip_detector_init:
            path = (
                Path(dbnet_model_path)
                if dbnet_model_path is not None
                else ensure_dbnet_onnx()
            )
            if dbnet_model_path is not None:
                path = ensure_dbnet_onnx(path)
            self._detector = LocalTextDetector(path)

        self._try_init_fsrcnn()

    def _try_init_fsrcnn(self) -> None:
        """dnn_superres + CUDA + FSRCNN .pb → GPU path; else CPU Bicubic (prompt contract)."""
        if self.fsrcnn_model_path is None or not self.fsrcnn_model_path.is_file():
            return
        try:
            from cv2 import dnn_superres  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.info("dnn_superres unavailable; will use CPU Bicubic upscale")
            return
        try:
            sr = dnn_superres.DnnSuperResImpl_create()
            sr.readModel(str(self.fsrcnn_model_path))
            try:
                cuda_count = int(cv2.cuda.getCudaEnabledDeviceCount())  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                cuda_count = 0
            if cuda_count > 0:
                try:
                    sr.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                    sr.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    self._fsrcnn_ready = True
                except Exception:  # noqa: BLE001
                    self._fsrcnn_ready = False
            else:
                self._fsrcnn_ready = False
            # Prompt: GPU FSRCNN only when CUDA is available; otherwise Bicubic ×1.5.
            if self._fsrcnn_ready:
                sr.setModel("fsrcnn", 2)
                self._fsrcnn_sr = sr
            else:
                self._fsrcnn_sr = None
        except Exception as exc:  # noqa: BLE001
            logger.info("FSRCNN init failed (%s); CPU Bicubic fallback", exc)
            self._fsrcnn_sr = None
            self._fsrcnn_ready = False

    def is_blurry(self, frame: np.ndarray, threshold: float = 100.0) -> bool:
        """True when Laplacian variance is below threshold (blurry / flat)."""
        if frame is None or frame.size == 0:
            return True
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return variance < float(threshold)

    def enhance_text_regions(
        self,
        frame: np.ndarray,
        bounding_boxes: list[BoundingBoxXYXY],
    ) -> list[np.ndarray]:
        """Per-box CLAHE → upscale → Otsu binary crops (values in {0, 255})."""
        if frame is None or frame.size == 0 or not bounding_boxes:
            return []
        h, w = int(frame.shape[0]), int(frame.shape[1])
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        crops: list[np.ndarray] = []
        use_gpu_fsrcnn = self._fsrcnn_sr is not None and self._fsrcnn_ready
        if use_gpu_fsrcnn:
            _print_info("[INFO] Upscaling bằng GPU FSRCNN")
        else:
            _print_info("[INFO] Upscaling bằng CPU Bicubic")

        for box in bounding_boxes:
            b = box.clamp(w, h)
            x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1), int(b.y1)
            if x1 <= x0 + 1 or y1 <= y0 + 1:
                continue
            roi = gray[y0:y1, x0:x1]
            if roi.size == 0:
                continue
            enhanced = clahe.apply(roi)
            try:
                if use_gpu_fsrcnn:
                    upscaled = self._fsrcnn_sr.upsample(enhanced)
                else:
                    nh = max(1, int(round(enhanced.shape[0] * _UPSCALE_FACTOR)))
                    nw = max(1, int(round(enhanced.shape[1] * _UPSCALE_FACTOR)))
                    upscaled = cv2.resize(enhanced, (nw, nh), interpolation=cv2.INTER_CUBIC)
            except Exception as exc:  # noqa: BLE001
                logger.warning("upscale_failed fallback_bicubic err=%s", exc)
                nh = max(1, int(round(enhanced.shape[0] * _UPSCALE_FACTOR)))
                nw = max(1, int(round(enhanced.shape[1] * _UPSCALE_FACTOR)))
                upscaled = cv2.resize(enhanced, (nw, nh), interpolation=cv2.INTER_CUBIC)

            _t, binary = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            crops.append(binary.astype(np.uint8))
        return crops

    def reset_tracking(self) -> None:
        self._previous_centroids = np.zeros((0, 2), dtype=np.float64)
        self._pending_boxes = None
        self._pending_wait_left = 0

    def _track_and_maybe_commit(
        self,
        boxes: list[BoundingBoxXYXY],
        *,
        frame_index: int,
    ) -> KeyframeResult | None:
        """
        Centroid tracking with fade-in delay.

        New centroids (min dist > threshold) start a pending wait; after
        ``fade_in_wait_frames`` additional sample sightings, commit a keyframe.
        """
        cents = centroids_from_boxes(boxes)
        if cents.size == 0:
            return None

        if self._pending_boxes is not None:
            # Still in fade-in wait for a previously detected new centroid cluster.
            self._pending_wait_left -= 1
            if self._pending_wait_left > 0:
                return None
            committed = KeyframeResult(
                frame_index=frame_index,
                frame_bgr=np.zeros((1, 1, 3), dtype=np.uint8),  # filled by extract()
                boxes=list(boxes) if boxes else list(self._pending_boxes),
                centroids=cents.copy(),
            )
            self._previous_centroids = cents.copy()
            self._pending_boxes = None
            self._pending_wait_left = 0
            return committed

        if not has_new_centroid(cents, self._previous_centroids, threshold_px=self.centroid_new_px):
            return None

        if self.fade_in_wait_frames <= 0:
            committed = KeyframeResult(
                frame_index=frame_index,
                frame_bgr=np.zeros((1, 1, 3), dtype=np.uint8),
                boxes=list(boxes),
                centroids=cents.copy(),
            )
            self._previous_centroids = cents.copy()
            return committed

        self._pending_boxes = list(boxes)
        self._pending_wait_left = int(self.fade_in_wait_frames)
        return None

    def extract(self, video_path: str | Path) -> list[KeyframeResult]:
        """Read video every ``sample_stride`` frames; return committed keyframes with crops."""
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Video not found: {path}")
        if self._detector is None:
            raise RuntimeError("SmartKeyframeExtractor has no LocalTextDetector")

        self.reset_tracking()
        results: list[KeyframeResult] = []
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                raise RuntimeError(f"Failed to open video: {path}")
            frame_index = 0
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if frame_index % self.sample_stride != 0:
                    frame_index += 1
                    continue

                if self.is_blurry(frame, threshold=self.blur_threshold):
                    logger.debug("skip_blurry frame=%s", frame_index)
                    frame_index += 1
                    continue

                try:
                    text_boxes = self._detector.detect(frame)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("detect_failed frame=%s err=%s", frame_index, exc)
                    frame_index += 1
                    continue

                h, w = int(frame.shape[0]), int(frame.shape[1])
                raw_boxes = text_boxes_to_xyxy(text_boxes, w, h)
                boxes = filter_valid_text_boxes(raw_boxes, w, h, frame_bgr=frame)
                if raw_boxes:
                    _print_info(
                        f"[INFO] Lọc ROI: Đã giảm từ {len(raw_boxes)} boxes rác "
                        f"xuống còn {len(boxes)} boxes phụ đề hợp lệ."
                    )
                if not boxes:
                    frame_index += 1
                    continue

                pending = self._track_and_maybe_commit(boxes, frame_index=frame_index)
                if pending is not None:
                    crops = self.enhance_text_regions(frame, pending.boxes)
                    pending.frame_bgr = frame.copy()
                    pending.enhanced_crops = crops
                    results.append(pending)
                    logger.info(
                        "keyframe_committed frame=%s boxes=%s crops=%s",
                        frame_index,
                        len(pending.boxes),
                        len(crops),
                    )

                frame_index += 1
        finally:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
        return results


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    video = Path(args[0]) if args else Path("test_video.mp4")
    if not video.is_file():
        print(f"[ERROR] Video not found: {video.resolve()}", file=sys.stderr)
        print("Usage: python -m src.media_pipeline.frame_sampling.smart_keyframe_extractor [video.mp4]")
        return 1
    logging.basicConfig(level=logging.INFO)
    extractor = SmartKeyframeExtractor()
    results = extractor.extract(video)
    print(f"[OK] Extracted {len(results)} keyframe(s) from {video}")
    for i, kf in enumerate(results):
        print(f"  [{i}] frame={kf.frame_index} boxes={len(kf.boxes)} crops={len(kf.enhanced_crops)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
