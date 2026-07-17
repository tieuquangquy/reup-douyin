"""Normalize Phase 2 OCR payloads into {timestamp_str: chinese_text}."""

from __future__ import annotations

from typing import Any, Mapping

from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode


def _join_box_texts(boxes: list[Any]) -> str:
    parts: list[str] = []
    for box in boxes:
        if isinstance(box, Mapping):
            text = str(box.get("text") or "").strip()
        else:
            text = str(box or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def flatten_ocr_chinese(ocr_data: Mapping[Any, Any] | list[Any]) -> dict[str, str]:
    """
    Accept either:
    - flat map: {0: "你好", "1000": "世界"}
    - Phase 2 `to_dict()` / frames list with boxes[].text
    """
    if isinstance(ocr_data, list):
        frames = ocr_data
        flat: dict[str, str] = {}
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            time_ms = frame.get("time_ms", 0)
            text = _join_box_texts(list(frame.get("boxes") or []))
            if text:
                flat[str(int(time_ms))] = text
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
            text = _join_box_texts(list(value.get("boxes") or []))
            time_key = value.get("time_ms", key)
        else:
            text = str(value or "").strip()
            time_key = key
        if not text:
            continue
        flat[str(time_key)] = text

    if not flat:
        raise TranslatorError(
            TranslatorErrorCode.EMPTY_INPUT,
            "ocr_data is empty — nothing to translate",
        )
    return flat
