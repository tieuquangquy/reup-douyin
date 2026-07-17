"""Phase 2.5: smart caption translator — Ops Translation settings (DB) first."""

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
    load_translator_settings,
)
from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.media_pipeline.translator.service import translate_subtitles

__all__ = [
    "DEFAULT_TRANSLATION_SYSTEM_PROMPT",
    "TranslatorSettings",
    "flatten_ocr_chinese",
    "load_translator_settings",
    "resolve_translator_settings",
    "translate_subtitles",
]
