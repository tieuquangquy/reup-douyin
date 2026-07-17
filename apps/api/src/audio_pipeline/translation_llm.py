from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.audio_pipeline.machine_translate import contains_cjk, mymemory_zh_to_vi
from src.audio_pipeline.providers import estimate_tts_duration_seconds
from src.audio_pipeline.types import TranslationDraftSegment, TranslationPreset

logger = logging.getLogger(__name__)

# Approx Vietnamese spoken syllables per second for length budgets.
VI_SYLLABLES_PER_SECOND = 4.5
FIT_RATIO = 1.15
# Keep chat-LLM repair short; MT recovery is cheaper than multi-round Ollama.
DEFAULT_CJK_REPAIR_ROUNDS = 1


class LlmClient(Protocol):
    provider_name: str

    def complete(self, prompt: str) -> str:
        ...


@dataclass
class FixedLlmClient:
    """Deterministic LLM stub for tests."""

    responses: list[str]
    provider_name: str = "fixed_llm"
    call_count: int = 0

    def complete(self, prompt: str) -> str:
        del prompt
        index = min(self.call_count, len(self.responses) - 1)
        self.call_count += 1
        return self.responses[index]


@dataclass
class GeminiHttpClient:
    api_key: str
    model: str = "gemini-2.0-flash"
    timeout_seconds: float = 90.0
    provider_name: str = "gemini"
    opener: object | None = None

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("gemini_api_key_missing")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            # Pro models may reason longer; keep output budget for ~one DialogueBeat.
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        open_fn = self.opener or urllib.request.urlopen
        try:
            with open_fn(request, timeout=self.timeout_seconds) as response:  # type: ignore[arg-type]
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"gemini_http_{exc.code}:{detail[:200]}") from exc
        return _extract_gemini_text(payload)


@dataclass
class OllamaHttpClient:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:14b"
    timeout_seconds: float = 120.0
    provider_name: str = "qwen_ollama"
    opener: object | None = None

    def complete(self, prompt: str) -> str:
        url = self.base_url.rstrip("/") + "/api/generate"
        body = {"model": self.model, "prompt": prompt, "stream": False}
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        open_fn = self.opener or urllib.request.urlopen
        try:
            with open_fn(request, timeout=self.timeout_seconds) as response:  # type: ignore[arg-type]
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ollama_http_{exc.code}:{detail[:200]}") from exc
        text = str(payload.get("response") or "").strip()
        if not text:
            raise RuntimeError("ollama_empty_response")
        return text


@dataclass
class OpenAiCompatibleHttpClient:
    """OpenAI Chat Completions API shape (OpenAI, OpenRouter, many third-party proxies)."""

    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 90.0
    provider_name: str = "openai_compatible"
    opener: object | None = None

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("openai_compatible_api_key_missing")
        if not self.model:
            raise RuntimeError("openai_compatible_model_missing")
        url = self.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        open_fn = self.opener or urllib.request.urlopen
        try:
            with open_fn(request, timeout=self.timeout_seconds) as response:  # type: ignore[arg-type]
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"openai_compatible_http_{exc.code}:{detail[:200]}") from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("openai_compatible_empty_response")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        text = ""
        if isinstance(message, dict):
            text = str(message.get("content") or "").strip()
        if not text:
            raise RuntimeError("openai_compatible_empty_response")
        return text


@dataclass
class DurationConstrainedTranslationProvider:
    """
    zh→vi translation with spoken-duration budget and optional rewrite loop.

    Primary client is typically Gemini free tier; fallback is local Qwen via Ollama.
    Fail-closed: Vietnamese that still contains Han characters is rejected after repair.
    """

    primary: LlmClient
    fallback: LlmClient | None = None
    max_rewrite_rounds: int = 2
    max_cjk_repair_rounds: int = DEFAULT_CJK_REPAIR_ROUNDS
    machine_translate: Callable[[str], str] | None = field(default=None)
    # When set (incl. from DB workspace settings), overrides file/env/builtin prompts.
    user_prompt: str | None = None
    provider_name: str = "duration_constrained_llm"
    fit_ratio: float = FIT_RATIO

    def __post_init__(self) -> None:
        if self.machine_translate is None:
            self.machine_translate = mymemory_zh_to_vi

    def translate(
        self,
        source_text: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float,
        source_confidence: float | None = None,
    ) -> TranslationDraftSegment:
        source = (source_text or "").strip()
        if not source:
            return TranslationDraftSegment(
                segment_index=0,
                translated_text="",
                translation_preset=preset,
                duration_budget_seconds=duration_budget_seconds,
                estimated_tts_duration_seconds=0.0,
                quality_flags=["empty_source"],
                metadata={"provider": self.provider_name},
            )

        flags: list[str] = []
        metadata: dict = {"provider": self.provider_name, "preset": str(preset)}
        if self.user_prompt is not None and self.user_prompt.strip():
            metadata["prompt_source"] = "workspace_db"
            flags.append("workspace_translation_prompt")

        # Gemini/LLM first for meaning quality; MyMemory only when LLM is down or CJK-dirty.
        try:
            if self.user_prompt is not None and self.user_prompt.strip():
                translate_prompt = _build_translate_prompt(
                    source,
                    preset,
                    duration_budget_seconds,
                    user_prompt=self.user_prompt,
                    load_settings=False,
                )
            else:
                translate_prompt = _build_translate_prompt(
                    source,
                    preset,
                    duration_budget_seconds,
                    load_settings=True,
                )
            client_used, text = self._complete_with_fallback(translate_prompt)
        except Exception as exc:
            logger.warning("translation_llm_unavailable", extra={"error": str(exc)})
            mt_recovery = self._try_machine_translate_recovery(source)
            if mt_recovery is not None:
                estimated = estimate_tts_duration_seconds(mt_recovery)
                flags.extend(["machine_translate_recovery", "needs_operator_review"])
                if duration_budget_seconds < 0.8:
                    flags.append("awkward_short_segment")
                return TranslationDraftSegment(
                    segment_index=0,
                    translated_text=mt_recovery,
                    translation_preset=preset,
                    duration_budget_seconds=duration_budget_seconds,
                    estimated_tts_duration_seconds=estimated,
                    quality_flags=list(dict.fromkeys(flags)),
                    metadata={
                        **metadata,
                        "provider": "mymemory",
                        "llm_provider": "mymemory",
                        "machine_translate": True,
                        "llm_error": str(exc)[:240],
                    },
                )
            from src.audio_pipeline.providers import PlaceholderVietnameseTranslationProvider

            draft = PlaceholderVietnameseTranslationProvider().translate(
                source,
                preset=preset,
                duration_budget_seconds=duration_budget_seconds,
                source_confidence=source_confidence,
            )
            return TranslationDraftSegment(
                segment_index=draft.segment_index,
                translated_text=draft.translated_text,
                translation_preset=draft.translation_preset,
                duration_budget_seconds=draft.duration_budget_seconds,
                estimated_tts_duration_seconds=draft.estimated_tts_duration_seconds,
                quality_flags=list(
                    dict.fromkeys([*draft.quality_flags, "translation_llm_unavailable", "needs_operator_review"])
                ),
                metadata={**draft.metadata, "llm_error": str(exc)[:240]},
            )

        metadata["llm_provider"] = client_used.provider_name
        metadata["provider"] = client_used.provider_name
        if client_used is not self.primary:
            flags.append("translation_fallback_used")

        text, cjk_flags, cjk_meta = self._enforce_vietnamese_only(
            source,
            text,
            preset=preset,
            duration_budget_seconds=duration_budget_seconds,
        )
        flags.extend(cjk_flags)
        metadata.update(cjk_meta)
        if "translation_gate_failed" in cjk_flags:
            estimated = 0.0
            flags.append("needs_operator_review")
            return TranslationDraftSegment(
                segment_index=0,
                translated_text="",
                translation_preset=preset,
                duration_budget_seconds=duration_budget_seconds,
                estimated_tts_duration_seconds=estimated,
                quality_flags=list(dict.fromkeys(flags)),
                metadata=metadata,
            )

        rewrite_count = 0
        for _ in range(max(0, self.max_rewrite_rounds)):
            estimated = estimate_tts_duration_seconds(text)
            if estimated <= duration_budget_seconds * self.fit_ratio:
                break
            rewrite_count += 1
            try:
                client_used, text = self._complete_with_fallback(
                    _build_shorten_prompt(
                        source,
                        text,
                        preset,
                        duration_budget_seconds,
                        user_prompt=self.user_prompt,
                    )
                )
            except Exception as exc:
                logger.warning("translation_rewrite_failed", extra={"error": str(exc)})
                flags.append("duration_rewrite_failed")
                break
            metadata["llm_provider"] = client_used.provider_name
            metadata["provider"] = client_used.provider_name
            text, cjk_flags, cjk_meta = self._enforce_vietnamese_only(
                source,
                text,
                preset=preset,
                duration_budget_seconds=duration_budget_seconds,
            )
            flags.extend(cjk_flags)
            metadata.update(cjk_meta)
            if "translation_gate_failed" in cjk_flags:
                flags.append("needs_operator_review")
                return TranslationDraftSegment(
                    segment_index=0,
                    translated_text="",
                    translation_preset=preset,
                    duration_budget_seconds=duration_budget_seconds,
                    estimated_tts_duration_seconds=0.0,
                    quality_flags=list(dict.fromkeys(flags)),
                    metadata=metadata,
                )

        if rewrite_count:
            flags.append("duration_rewrite_applied")
            metadata["rewrite_rounds"] = rewrite_count

        estimated = estimate_tts_duration_seconds(text)
        if source_confidence is not None and source_confidence < 0.65:
            flags.append("low_confidence_source")
            flags.append("needs_operator_review")
        if estimated > duration_budget_seconds * self.fit_ratio:
            flags.append("translation_too_long_for_slot")
            flags.append("needs_operator_review")
        if duration_budget_seconds < 0.8:
            flags.append("awkward_short_segment")
        if "translation_fallback_used" in flags:
            flags.append("needs_operator_review")

        return TranslationDraftSegment(
            segment_index=0,
            translated_text=text.strip(),
            translation_preset=preset,
            duration_budget_seconds=duration_budget_seconds,
            estimated_tts_duration_seconds=estimated,
            quality_flags=list(dict.fromkeys(flags)),
            metadata=metadata,
        )

    def _enforce_vietnamese_only(
        self,
        source: str,
        text: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float,
    ) -> tuple[str, list[str], dict]:
        """Repair VI that still contains Han characters; micro-chunk before fail-closed."""
        flags: list[str] = []
        metadata: dict = {}
        current = (text or "").strip()
        if not contains_cjk(current):
            return current, flags, metadata

        flags.append("vi_contains_source_script")
        metadata["rejected_vi"] = current[:240]

        # Recovery MT on Chinese source before more slow chat-LLM/Ollama rounds.
        mt_text = self._try_machine_translate_recovery(source)
        if mt_text is not None:
            flags.append("machine_translate_applied")
            metadata["machine_translate"] = True
            return mt_text, flags, metadata
        flags.append("machine_translate_failed")

        repair_rounds = 0
        for _ in range(max(0, self.max_cjk_repair_rounds)):
            repair_rounds += 1
            try:
                _client, current = self._complete_with_fallback(
                    _build_cjk_repair_prompt(source, current, user_prompt=self.user_prompt)
                )
            except Exception as exc:
                logger.warning("translation_cjk_repair_failed", extra={"error": str(exc)})
                flags.append("cjk_repair_failed")
                break
            if not contains_cjk(current):
                metadata["cjk_repair_rounds"] = repair_rounds
                flags.append("cjk_repair_applied")
                return current.strip(), flags, metadata

        metadata["cjk_repair_rounds"] = repair_rounds

        chunked = self._retranslate_source_in_chunks(
            source,
            preset=preset,
            duration_budget_seconds=duration_budget_seconds,
        )
        if chunked is not None and chunked.strip() and not contains_cjk(chunked):
            flags.append("cjk_chunk_retranslate_applied")
            metadata["cjk_chunk_retranslate"] = True
            # Drop gate-failed path; keep vi_contains_source_script for observability.
            return chunked.strip(), flags, metadata

        flags.append("translation_gate_failed")
        return "", flags, metadata

    def _try_machine_translate_recovery(self, source: str) -> str | None:
        mt_fn = self.machine_translate
        if mt_fn is None:
            return None
        try:
            mt_text = (mt_fn(source) or "").strip()
        except Exception as exc:
            logger.warning("machine_translate_failed", extra={"error": str(exc)[:200]})
            return None
        if mt_text and not contains_cjk(mt_text):
            return mt_text
        return None

    def _retranslate_source_in_chunks(
        self,
        source: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float,
    ) -> str | None:
        """Re-run literal translate on smaller Chinese pieces when whole-beat VI stays dirty."""
        from src.audio_pipeline.stt_funasr import split_untimed_asr_text

        cleaned = (source or "").strip()
        if not cleaned:
            return None
        parts = split_untimed_asr_text(cleaned, max_chars=24)
        if len(parts) <= 1 and len(cleaned) > 12:
            mid = max(1, len(cleaned) // 2)
            parts = [cleaned[:mid].strip(), cleaned[mid:].strip()]
            parts = [part for part in parts if part]
        if len(parts) <= 1:
            return None

        total_chars = sum(max(1, len(part)) for part in parts)
        pieces: list[str] = []
        for part in parts:
            share = max(1, len(part)) / total_chars
            budget = max(0.8, float(duration_budget_seconds) * share)
            try:
                if self.user_prompt is not None and self.user_prompt.strip():
                    chunk_prompt = _build_translate_prompt(
                        part,
                        preset,
                        budget,
                        user_prompt=self.user_prompt,
                        load_settings=False,
                    )
                else:
                    chunk_prompt = _build_translate_prompt(part, preset, budget, load_settings=True)
                _client, piece = self._complete_with_fallback(chunk_prompt)
            except Exception as exc:
                logger.warning("translation_chunk_retranslate_failed", extra={"error": str(exc)})
                return None
            if contains_cjk(piece):
                try:
                    _client, piece = self._complete_with_fallback(
                        _build_cjk_repair_prompt(part, piece, user_prompt=self.user_prompt)
                    )
                except Exception as exc:
                    logger.warning("translation_chunk_repair_failed", extra={"error": str(exc)})
                    return None
            piece = piece.strip()
            if not piece or contains_cjk(piece):
                return None
            pieces.append(piece)
        return " ".join(pieces)

    def _complete_with_fallback(self, prompt: str) -> tuple[LlmClient, str]:
        try:
            return self.primary, _clean_model_text(self.primary.complete(prompt))
        except Exception as primary_exc:
            logger.warning(
                "translation_primary_failed",
                extra={"provider": self.primary.provider_name, "error": str(primary_exc)},
            )
            if self.fallback is None:
                raise
            try:
                return self.fallback, _clean_model_text(self.fallback.complete(prompt))
            except Exception as fallback_exc:
                logger.warning(
                    "translation_fallback_failed",
                    extra={"provider": self.fallback.provider_name, "error": str(fallback_exc)},
                )
                raise fallback_exc from primary_exc


def resolve_translation_user_prompt(
    inline: str | None = None,
    file_path: str | None = None,
    *,
    base_dir: Path | None = None,
) -> str | None:
    """
    Load operator-owned dialogue translation system prompt.

    File path wins over inline when the file exists and contains non-comment text.
    """
    path_raw = (file_path or "").strip()
    if path_raw:
        path = Path(path_raw)
        if not path.is_absolute():
            api_root = Path(__file__).resolve().parents[2]  # apps/api
            candidates = [(base_dir or Path.cwd()) / path, api_root / path]
            path = next((c.resolve() for c in candidates if c.resolve().is_file()), candidates[0].resolve())
        else:
            path = path.resolve()
        if path.is_file():
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("translation_user_prompt_file_unreadable", extra={"path": str(path), "error": str(exc)})
            else:
                if _prompt_file_has_body(raw):
                    return raw.strip()
        else:
            logger.warning("translation_user_prompt_file_missing", extra={"path": str(path)})

    inline_text = (inline or "").strip()
    return inline_text or None


def _prompt_file_has_body(raw: str) -> bool:
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def _load_configured_translation_user_prompt() -> str | None:
    from src.core.settings import get_settings

    cfg = get_settings()
    return resolve_translation_user_prompt(
        inline=getattr(cfg, "audio_translation_user_prompt", None),
        file_path=getattr(cfg, "audio_translation_user_prompt_file", None),
    )


def _build_translate_prompt(
    source_text: str,
    preset: TranslationPreset,
    budget_seconds: float,
    *,
    user_prompt: str | None = None,
    load_settings: bool = False,
) -> str:
    """
    Build the main ZH→VI prompt for one DialogueBeat.

    When an operator prompt is configured (arg or settings), use it as-is and only
    append the Chinese source. Built-in preset templates apply only when unset.
    """
    if user_prompt is not None:
        custom = user_prompt.strip() or None
    elif load_settings:
        custom = _load_configured_translation_user_prompt()
    else:
        custom = None
    source = (source_text or "").strip()
    if custom:
        return f"{custom}\n\nChinese source:\n{source}"

    syllable_budget = max(4, int(round(budget_seconds * VI_SYLLABLES_PER_SECOND)))
    if preset == TranslationPreset.LITERAL_SAFE:
        return (
            "You are doing a literal Chinese→Vietnamese translation for dubbed short video.\n"
            "Mode: literal_safe.\n"
            "Translate ONLY the spoken meaning in the Chinese source.\n"
            "Do not add any words, phrases, hooks, CTAs, opinions, or explanations that are not in the source.\n"
            "Do not omit meaning that is present in the source.\n"
            "Use correct Vietnamese for cooking, diet/fat-loss, and social CTAs "
            "(e.g. 关注=follow/subscribe, not gambling bets; 减脂=cut fat / fat-loss).\n"
            "Prefer natural spoken Vietnamese wording while staying faithful — avoid awkward word-for-word calques.\n"
            "Output must be 100% Vietnamese. Never leave Chinese characters in the output.\n"
            f"Keep the line speakable in about {budget_seconds:.1f} seconds "
            f"(roughly {syllable_budget} Vietnamese syllables) without inventing filler.\n"
            "Return ONLY the Vietnamese translation text.\n\n"
            f"Chinese source:\n{source_text}"
        )
    if preset == TranslationPreset.NATURAL_VIRAL:
        return (
            "You are translating Douyin spoken Chinese into Vietnamese narration for dubbing.\n"
            "Mode: natural_viral.\n"
            "Style: natural spoken Vietnamese suitable for short-form video — clear, punchy, easy to say aloud.\n"
            "Keep core meaning faithful. You may smooth phrasing and light spoken rhythm; "
            "do not invent facts, numbers, ingredients, or CTAs absent from the source.\n"
            "Do not add emojis, hashtags, or meta explanations.\n"
            "Output must be 100% Vietnamese. Never leave Chinese characters in the output.\n"
            f"Target spoken duration: about {budget_seconds:.1f} seconds "
            f"(roughly {syllable_budget} Vietnamese syllables).\n"
            "Return ONLY the Vietnamese translation text.\n\n"
            f"Chinese source:\n{source_text}"
        )
    return (
        "You are translating Douyin spoken Chinese into Vietnamese narration for dubbing.\n"
        "Mode: affiliate_soft_sell.\n"
        "Style: natural Vietnamese with soft recommendation tone, not spammy.\n"
        f"Target spoken duration: about {budget_seconds:.1f} seconds "
        f"(roughly {syllable_budget} Vietnamese syllables).\n"
        "Keep meaning faithful. Do not add emojis, hashtags, or explanations.\n"
        "Output must be 100% Vietnamese. Never leave Chinese characters in the output.\n"
        "Return ONLY the Vietnamese translation text.\n\n"
        f"Chinese source:\n{source_text}"
    )


def _build_shorten_prompt(
    source_text: str,
    previous_vi: str,
    preset: TranslationPreset,
    budget_seconds: float,
    *,
    user_prompt: str | None = None,
) -> str:
    del preset
    syllable_budget = max(4, int(round(budget_seconds * VI_SYLLABLES_PER_SECOND)))
    custom = (user_prompt or "").strip()
    if custom:
        # Operator Translation prompt is authority; only add the shorten task frame.
        return (
            f"{custom}\n\n"
            "Task: shorten the Vietnamese dubbing line so it can be spoken within the time budget "
            f"({budget_seconds:.1f}s, ~{syllable_budget} syllables). "
            "Still obey every operator rule above.\n"
            "Return ONLY the revised Vietnamese text.\n\n"
            f"Chinese source:\n{source_text}\n\n"
            f"Current Vietnamese (too long):\n{previous_vi}"
        )
    return (
        "Shorten this Vietnamese dubbing line so it can be spoken within the time budget "
        f"({budget_seconds:.1f}s, ~{syllable_budget} syllables) while keeping the same meaning.\n"
        "Output must be 100% Vietnamese with zero Chinese characters.\n"
        "Return ONLY the revised Vietnamese text.\n\n"
        f"Chinese source (meaning reference only):\n{source_text}\n\n"
        f"Current Vietnamese (too long):\n{previous_vi}"
    )


def _build_cjk_repair_prompt(
    source_text: str,
    dirty_vi: str,
    *,
    user_prompt: str | None = None,
) -> str:
    custom = (user_prompt or "").strip()
    if custom:
        # Operator Translation prompt is authority; only add the CJK-clean task frame.
        return (
            f"{custom}\n\n"
            "Task: the Vietnamese dubbing line below still contains Chinese characters. "
            "Rewrite it as complete Vietnamese only (zero Han characters). "
            "Still obey every operator rule above.\n"
            "Return ONLY the cleaned Vietnamese text.\n\n"
            f"Chinese source:\n{source_text}\n\n"
            f"Dirty Vietnamese:\n{dirty_vi}"
        )
    return (
        "The Vietnamese dubbing line below still contains Chinese characters. "
        "Rewrite it as complete Vietnamese only.\n"
        "Do not leave any Han/Chinese characters.\n"
        "Do not add meaning that is not in the Chinese source.\n"
        "Return ONLY the cleaned Vietnamese text.\n\n"
        f"Chinese source:\n{source_text}\n\n"
        f"Dirty Vietnamese:\n{dirty_vi}"
    )


def _clean_model_text(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[-1].strip()
    return cleaned.strip().strip('"').strip("'")


def _extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("gemini_empty_candidates")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
    joined = "\n".join(t for t in texts if t.strip()).strip()
    if not joined:
        raise RuntimeError("gemini_empty_text")
    return joined
