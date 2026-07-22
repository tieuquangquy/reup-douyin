"""Lightweight PP-OCR CTC recognizer used only as a local text verifier."""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE_SHAPE = (3, 48, 320)


@dataclass(frozen=True)
class LocalRecognition:
    text: str
    confidence: float
    valid_char_ratio: float


def _is_text_character(char: str) -> bool:
    if not char or char.isspace():
        return False
    category = unicodedata.category(char)
    return category[0] in {"L", "N"}


def preprocess_bgr_for_text_recognition(
    crop_bgr: np.ndarray,
    *,
    image_shape: tuple[int, int, int] = _DEFAULT_IMAGE_SHAPE,
) -> np.ndarray:
    """Aspect-preserving PP-OCR normalization with right-side zero padding."""
    if crop_bgr is None or crop_bgr.ndim != 3 or crop_bgr.shape[2] != 3:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Expected HxWx3 BGR line crop, got {getattr(crop_bgr, 'shape', None)}",
        )
    channels, target_h, target_w = (int(v) for v in image_shape)
    height, width = crop_bgr.shape[:2]
    if channels != 3 or height < 2 or width < 2:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Invalid recognizer crop/shape: crop={width}x{height} shape={image_shape}",
        )
    resized_w = min(target_w, max(1, int(math.ceil(target_h * width / float(height)))))
    resized = cv2.resize(crop_bgr, (resized_w, target_h), interpolation=cv2.INTER_LINEAR)
    normalized = resized.astype(np.float32).transpose((2, 0, 1)) / 255.0
    normalized = (normalized - 0.5) / 0.5
    canvas = np.zeros((channels, target_h, target_w), dtype=np.float32)
    canvas[:, :, :resized_w] = normalized
    return canvas[None, ...]


def ctc_decode(logits: np.ndarray, characters: list[str]) -> LocalRecognition:
    """Greedy CTC decode (blank index zero, dictionary indices start at one)."""
    scores = np.asarray(logits, dtype=np.float32)
    if scores.ndim == 2:
        scores = scores[None, ...]
    if scores.ndim != 3 or scores.shape[0] < 1:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Unexpected recognizer output shape {scores.shape}",
        )
    sample = scores[0]
    row_sums = np.sum(sample, axis=1, keepdims=True)
    if (
        float(np.min(sample)) >= 0.0
        and float(np.max(sample)) <= 1.0 + 1e-4
        and np.allclose(row_sums, 1.0, atol=1e-3)
    ):
        probabilities = sample
    else:
        shifted = sample - np.max(sample, axis=1, keepdims=True)
        probabilities = np.exp(shifted)
        probabilities /= np.maximum(np.sum(probabilities, axis=1, keepdims=True), 1e-8)
    token_ids = np.argmax(probabilities, axis=1)
    token_probs = probabilities[np.arange(probabilities.shape[0]), token_ids]

    emitted: list[str] = []
    confidences: list[float] = []
    previous = -1
    for token_id, probability in zip(token_ids.tolist(), token_probs.tolist()):
        if token_id != 0 and token_id != previous:
            char_index = token_id - 1
            if 0 <= char_index < len(characters):
                emitted.append(characters[char_index])
                confidences.append(float(probability))
        previous = token_id
    text = "".join(emitted).strip()
    valid_count = sum(1 for char in text if _is_text_character(char))
    non_space_count = sum(1 for char in text if not char.isspace())
    return LocalRecognition(
        text=text,
        confidence=float(np.mean(confidences)) if confidences else 0.0,
        valid_char_ratio=float(valid_count / non_space_count) if non_space_count else 0.0,
    )


def ctc_decode_batch(
    logits: np.ndarray,
    characters: list[str],
) -> list[LocalRecognition]:
    """Decode every sample from one batched CTC output."""
    scores = np.asarray(logits, dtype=np.float32)
    if scores.ndim == 2:
        scores = scores[None, ...]
    if scores.ndim != 3:
        raise FrameSamplingError(
            FrameSamplingErrorCode.ONNX_INFER_FAILED,
            f"Unexpected recognizer output shape {scores.shape}",
        )
    return [ctc_decode(scores[index : index + 1], characters) for index in range(scores.shape[0])]


class LocalTextRecognizer:
    """CPU ONNX recognizer. Its text is evidence; Cloud OCR remains content authority."""

    def __init__(self, model_path: Path | str, dictionary_path: Path | str):
        model = Path(model_path)
        dictionary = Path(dictionary_path)
        if not model.is_file() or not dictionary.is_file():
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_MISSING,
                f"Local recognizer assets missing: model={model.name} dict={dictionary.name}",
            )
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_MISSING,
                "onnxruntime is required for local text verification",
            ) from exc
        self._characters = [
            line.rstrip("\r\n")
            for line in dictionary.read_text(encoding="utf-8").splitlines()
            if line.rstrip("\r\n")
        ]
        # PaddleOCR CTC decoders append a literal space after dictionary characters.
        if not self._characters or self._characters[-1] != " ":
            self._characters.append(" ")
        try:
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(model),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            input_meta = self._session.get_inputs()[0]
            self._input_name = input_meta.name
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_LOAD_FAILED,
                f"Failed to load local text recognizer ({model.name}): {exc}",
            ) from exc
        self.model_path = model
        self.dictionary_path = dictionary
        logger.info("local_text_recognizer_ready model=%s", model.name)

    def recognize(self, crop_bgr: np.ndarray) -> LocalRecognition:
        return self.recognize_batch([crop_bgr])[0]

    def recognize_batch(self, crops_bgr: list[np.ndarray]) -> list[LocalRecognition]:
        if not crops_bgr:
            return []
        tensor = np.concatenate(
            [preprocess_bgr_for_text_recognition(crop) for crop in crops_bgr],
            axis=0,
        )
        try:
            outputs = self._session.run(None, {self._input_name: tensor})
        except Exception as exc:  # noqa: BLE001
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_INFER_FAILED,
                f"Local text recognizer inference failed: {exc}",
            ) from exc
        if not outputs:
            return [
                LocalRecognition(text="", confidence=0.0, valid_char_ratio=0.0)
                for _crop in crops_bgr
            ]
        results = ctc_decode_batch(outputs[0], self._characters)
        if len(results) != len(crops_bgr):
            raise FrameSamplingError(
                FrameSamplingErrorCode.ONNX_INFER_FAILED,
                "Local text recognizer batch size mismatch: "
                f"input={len(crops_bgr)} output={len(results)}",
            )
        return results
