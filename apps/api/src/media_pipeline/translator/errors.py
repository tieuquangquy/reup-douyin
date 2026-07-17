"""Phase 2.5 translator errors."""

from __future__ import annotations

from enum import Enum


class TranslatorErrorCode(str, Enum):
    CONFIG_MISSING = "CONFIG_MISSING"
    EMPTY_INPUT = "EMPTY_INPUT"
    LLM_FAILED = "LLM_FAILED"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class TranslatorError(Exception):
    def __init__(self, code: TranslatorErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
