"""Persistent ZH→VI translation memory keyed by model + prompt + canonical ZH."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.media_pipeline.translator.normalize import canonical_zh

logger = logging.getLogger(__name__)

ENV_MEMORY_PATH = "TRANSLATE_MEMORY_PATH"


def default_memory_path() -> Path:
    override = os.environ.get(ENV_MEMORY_PATH, "").strip()
    if override:
        return Path(override)
    # apps/api/.cache/translate_memory.json
    api_root = Path(__file__).resolve().parents[3]
    return api_root / ".cache" / "translate_memory.json"


def memory_cache_key(*, model_name: str, system_prompt: str, zh: str) -> str:
    prompt_fp = hashlib.sha256(str(system_prompt or "").encode("utf-8")).hexdigest()[:16]
    raw = f"{model_name}|{prompt_fp}|{canonical_zh(zh)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TranslationMemory:
    """JSON file store: cache_key → vietnamese."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_memory_path()
        self._data: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            self._data = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("translate_memory_load_failed path=%s err=%s", self.path, exc)
            self._data = {}
            return
        if isinstance(raw, dict):
            entries = raw.get("entries") if "entries" in raw else raw
            if isinstance(entries, dict):
                self._data = {
                    str(k): str(v).strip()
                    for k, v in entries.items()
                    if str(v or "").strip()
                }
                return
        self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"version": 1, "entries": dict(self._data)}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, *, model_name: str, system_prompt: str, zh: str) -> str | None:
        self.load()
        key = memory_cache_key(model_name=model_name, system_prompt=system_prompt, zh=zh)
        hit = self._data.get(key)
        return hit if hit else None

    def put(self, *, model_name: str, system_prompt: str, zh: str, vi: str) -> None:
        text = str(vi or "").strip()
        if not text or text == "...":
            return
        self.load()
        key = memory_cache_key(model_name=model_name, system_prompt=system_prompt, zh=zh)
        self._data[key] = text
