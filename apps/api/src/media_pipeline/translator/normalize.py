"""Normalize Phase 2 OCR payloads into {timestamp_str: chinese_text}.

Each OCR box with Chinese (CJK) becomes its own key ``{time_ms}#{box_index}``
so Caption AI and render can cover+burn VI **per label**. Latin/VI-only boxes
(e.g. existing Vietnamese hard-subs, dates) are skipped.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode


def _box_text(box: Any) -> str:
    if isinstance(box, Mapping):
        return str(box.get("text") or "").strip()
    return str(box or "").strip()


def flatten_ocr_chinese(ocr_data: Mapping[Any, Any] | list[Any]) -> dict[str, str]:
    """
    Accept either:
    - flat map: {0: "你好", "1000": "世界"}
    - Phase 2 `to_dict()` / frames list with boxes[].text → per-box CJK keys
    """
    if isinstance(ocr_data, list):
        frames = ocr_data
        flat: dict[str, str] = {}
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            time_ms = int(frame.get("time_ms", 0) or 0)
            raw_boxes = [b for b in list(frame.get("boxes") or []) if isinstance(b, Mapping)]
            if not raw_boxes:
                continue
            box_index = 0
            for box in raw_boxes:
                text = _box_text(box)
                if not text or not contains_cjk(text):
                    continue
                key = f"{time_ms}#{box_index}"
                flat[key] = text
                # Convenience alias for first CJK box on this timestamp.
                if box_index == 0 and str(time_ms) not in flat:
                    flat[str(time_ms)] = text
                box_index += 1
        if not flat:
            raise TranslatorError(
                TranslatorErrorCode.EMPTY_INPUT,
                "OCR frame list has no Chinese text to translate",
            )
        return flat

    if "frames" in ocr_data and isinstance(ocr_data.get("frames"), list):
        return flatten_ocr_chinese(list(ocr_data["frames"]))

    flat = {}
    for key, value in ocr_data.items():
        if key in {"provider", "frame_count", "warnings", "frames"}:
            continue
        if isinstance(value, Mapping) and "boxes" in value:
            texts = [
                _box_text(b)
                for b in list(value.get("boxes") or [])
                if contains_cjk(_box_text(b))
            ]
            texts = [t for t in texts if t]
            text = " ".join(texts)
            time_key = value.get("time_ms", key)
        else:
            text = str(value or "").strip()
            time_key = key
            if text and not contains_cjk(text):
                continue
        if not text:
            continue
        flat[str(time_key)] = text

    if not flat:
        raise TranslatorError(
            TranslatorErrorCode.EMPTY_INPUT,
            "No Chinese text to translate",
        )
    return flat
