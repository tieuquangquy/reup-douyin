from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from src.audio_pipeline.types import TranscriptionUnit

logger = logging.getLogger(__name__)

_CAPTION_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n])\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n；;])\s*")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[，、,])\s*")
# Soft cap so untimed FunASR blobs become speakable/translatable DialogueBeats.
MAX_UNTIMED_BEAT_CHARS = 48

# First-time ModelScope paraformer download can take several minutes on slow links.
DEFAULT_FUNASR_TIMEOUT_SECONDS = 900.0
DEFAULT_FUNASR_HEARTBEAT_SECONDS = 15.0


def split_untimed_asr_text(text: str, *, max_chars: int = MAX_UNTIMED_BEAT_CHARS) -> list[str]:
    """Split an untimed ASR blob into sentence/clause/char chunks for DialogueBeats."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(cleaned) if part and part.strip()]
    if not parts:
        parts = [cleaned]

    expanded: list[str] = []
    limit = max(8, int(max_chars))
    for part in parts:
        if len(part) <= limit:
            expanded.append(part)
            continue
        clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(part) if c and c.strip()]
        if len(clauses) <= 1:
            expanded.extend(_chunk_text(part, limit))
            continue
        for clause in clauses:
            if len(clause) <= limit:
                expanded.append(clause)
            else:
                expanded.extend(_chunk_text(clause, limit))
    return expanded


def _chunk_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars) if text[index : index + max_chars]]


def expand_untimed_funasr_units(units: list[TranscriptionUnit]) -> list[TranscriptionUnit]:
    """Keep funasr_untimed blobs as one DialogueBeat (no sentence/clause/char split).

    Mid-sentence chops hurt operator review; duration fit still maps the single beat
    onto [0, media duration]. ``split_untimed_asr_text`` remains for translation
    recovery chunking only.
    """
    return list(units or [])


def split_caption_into_timed_units(
    caption: str,
    *,
    duration_seconds: float,
    flags: list[str] | None = None,
) -> list[TranscriptionUnit]:
    cleaned = (caption or "").strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in _CAPTION_SPLIT_RE.split(cleaned) if part and part.strip()]
    if not parts:
        parts = [cleaned]
    total_chars = sum(max(1, len(part)) for part in parts)
    duration = max(1.0, float(duration_seconds or 1.0))
    cursor = 0.0
    units: list[TranscriptionUnit] = []
    shared_flags = list(flags or ["caption_fallback", "caption_segmented"])
    for index, part in enumerate(parts):
        share = max(1, len(part)) / total_chars
        span = duration * share
        start = cursor
        end = duration if index == len(parts) - 1 else min(duration, cursor + span)
        if end <= start:
            end = start + 0.2
        cursor = end
        units.append(
            TranscriptionUnit(
                text=part,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                confidence=0.55,
                flags=list(shared_flags),
                raw_payload={"source": "segmented_caption", "segment_index": index},
            )
        )
    return units


def parse_funasr_generate_result(raw: Any) -> list[TranscriptionUnit]:
    """Normalize FunASR `generate()` payloads into TranscriptionUnit rows."""
    if raw is None:
        return []
    payloads = raw if isinstance(raw, list) else [raw]
    units: list[TranscriptionUnit] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        sentence_info = item.get("sentence_info") or item.get("sentences") or []
        if isinstance(sentence_info, list) and sentence_info:
            for sentence in sentence_info:
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                start_ms = float(sentence.get("start") if sentence.get("start") is not None else sentence.get("start_ms") or 0)
                end_ms = float(sentence.get("end") if sentence.get("end") is not None else sentence.get("end_ms") or start_ms + 500)
                # FunASR commonly returns milliseconds for sentence_info.
                if end_ms > 50 or start_ms > 50:
                    start_s = start_ms / 1000.0
                    end_s = end_ms / 1000.0
                else:
                    start_s = start_ms
                    end_s = max(end_ms, start_ms + 0.2)
                units.append(
                    TranscriptionUnit(
                        text=text,
                        start_seconds=round(start_s, 3),
                        end_seconds=round(max(end_s, start_s + 0.05), 3),
                        confidence=float(sentence.get("confidence") or 0.85),
                        flags=["funasr"],
                        raw_payload={"provider": "funasr", "sentence": sentence},
                    )
                )
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        units.append(
            TranscriptionUnit(
                text=text,
                start_seconds=0.0,
                # Temporary until fit_funasr_units_to_duration applies video duration.
                end_seconds=max(1.0, len(text) / 4.0),
                confidence=0.8,
                flags=["funasr", "funasr_untimed"],
                raw_payload={"provider": "funasr", "item": item},
            )
        )
    return units


def fit_funasr_units_to_duration(
    units: list[TranscriptionUnit],
    *,
    duration_seconds: float | None,
) -> list[TranscriptionUnit]:
    """
    Keep ASR timing inside the source video window.

    FunASR sometimes returns a single text blob without sentence_info. The
    char-rate heuristic then invents ends far past the real video (e.g. 3min for
    a 74s clip). When duration is known, redistribute/clamp onto [0, duration].
    """
    if not units:
        return units
    duration = float(duration_seconds or 0.0)
    if duration <= 0:
        return expand_untimed_funasr_units(units)

    units = expand_untimed_funasr_units(units)
    untimed = any("funasr_untimed" in (unit.flags or []) for unit in units)
    max_end = max(float(unit.end_seconds) for unit in units)
    if not untimed and max_end <= duration * 1.05:
        return units

    if untimed:
        total_chars = sum(max(1, len(unit.text or "")) for unit in units)
        cursor = 0.0
        fitted: list[TranscriptionUnit] = []
        for index, unit in enumerate(units):
            share = max(1, len(unit.text or "")) / total_chars
            span = duration * share
            start = cursor
            end = duration if index == len(units) - 1 else min(duration, cursor + span)
            if end <= start:
                end = min(duration, start + 0.2)
            cursor = end
            flags = list(unit.flags or [])
            if "duration_fit" not in flags:
                flags.append("duration_fit")
            fitted.append(
                replace(
                    unit,
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    flags=flags,
                )
            )
        return fitted

    # Timed sentences that overrun the media: proportional scale into the window.
    scale = duration / max_end if max_end > 0 else 1.0
    fitted = []
    for unit in units:
        flags = list(unit.flags or [])
        if "duration_fit" not in flags:
            flags.append("duration_fit")
        start = max(0.0, float(unit.start_seconds) * scale)
        end = max(start + 0.05, float(unit.end_seconds) * scale)
        fitted.append(
            replace(
                unit,
                start_seconds=round(min(start, duration), 3),
                end_seconds=round(min(end, duration), 3),
                flags=flags,
            )
        )
    return fitted


def run_with_timeout(
    fn: Callable[[], Any],
    *,
    timeout_seconds: float,
    on_tick: Callable[[], None] | None = None,
    tick_seconds: float = DEFAULT_FUNASR_HEARTBEAT_SECONDS,
) -> Any:
    """
    Run ``fn`` in a worker thread and abort waiting after ``timeout_seconds``.

    Optional ``on_tick`` fires while still waiting so callers can heartbeat job
    progress during first-time model downloads. The worker thread is abandoned on
    timeout (Windows-safe; no SIGALRM). Callers should treat that as fail-closed.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn)
        deadline = time.monotonic() + float(timeout_seconds)
        poll = max(0.05, float(tick_seconds or DEFAULT_FUNASR_HEARTBEAT_SECONDS))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                future.cancel()
                raise TimeoutError(f"funasr_timed_out_after_{timeout_seconds:.0f}s")
            try:
                return future.result(timeout=min(poll, remaining))
            except FuturesTimeoutError:
                if on_tick is not None:
                    try:
                        on_tick()
                    except Exception:
                        logger.exception("funasr_timeout_tick_failed")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


ResolveAudioPath = Callable[[str], str | None]
FunasrRunner = Callable[[str], Any]
LifecycleHook = Callable[[str], None]


@dataclass
class FunasrSttProvider:
    """
    Free Chinese ASR via FunASR Paraformer when installed.

    Douyin caption/title/hashtags are NOT dialogue. When FunASR is unavailable,
    times out, fails, or returns no speech units, this provider returns [] so
    Checkpoint #1 never invents DialogueBeats from metadata caption.
    """

    provider_name: str = "funasr_paraformer"
    resolve_audio_path: ResolveAudioPath | None = None
    funasr_runner: FunasrRunner | None = None
    force_unavailable: bool = False
    timeout_seconds: float = DEFAULT_FUNASR_TIMEOUT_SECONDS
    heartbeat_seconds: float = DEFAULT_FUNASR_HEARTBEAT_SECONDS
    on_lifecycle: LifecycleHook | None = None
    # Kept for callers/tests that inspect provider defaults; no longer used to invent beats.
    fallback_flags: list[str] = field(default_factory=lambda: ["funasr_unavailable", "caption_not_dialogue"])

    def transcribe(
        self,
        audio_storage_key: str,
        *,
        source_caption: str | None = None,
        duration_seconds: float | None = None,
    ) -> list[TranscriptionUnit]:
        _ = source_caption  # Douyin caption must not become DialogueBeats
        if self.force_unavailable:
            logger.warning(
                "funasr_unavailable_no_caption_dialogue",
                extra={"audio_storage_key": audio_storage_key},
            )
            return []

        try:
            units = self._transcribe_with_funasr(
                audio_storage_key,
                duration_seconds=duration_seconds,
            )
        except TimeoutError as exc:
            self._emit("funasr_timed_out")
            logger.warning(
                "funasr_transcribe_timed_out",
                extra={
                    "audio_storage_key": audio_storage_key,
                    "timeout_seconds": self.timeout_seconds,
                    "error": str(exc),
                },
            )
            return []
        except Exception as exc:
            logger.warning(
                "funasr_transcribe_failed",
                extra={"audio_storage_key": audio_storage_key, "error": str(exc)},
            )
            return []

        return units or []

    def _emit(self, event: str) -> None:
        if self.on_lifecycle is None:
            return
        try:
            self.on_lifecycle(event)
        except Exception:
            logger.exception("funasr_lifecycle_hook_failed", extra={"event": event})

    def _transcribe_with_funasr(
        self,
        audio_storage_key: str,
        *,
        duration_seconds: float | None = None,
    ) -> list[TranscriptionUnit]:
        runner = self.funasr_runner or _default_funasr_runner
        path_resolver = self.resolve_audio_path or (lambda _key: None)
        audio_path = path_resolver(audio_storage_key)
        if not audio_path:
            raise FileNotFoundError(f"Could not resolve audio path for {audio_storage_key}")
        # Injected runners are used in unit tests with synthetic paths.
        if self.funasr_runner is None and not Path(audio_path).exists():
            raise FileNotFoundError(audio_path)

        self._emit("funasr_started")
        logger.info(
            "funasr_transcribe_started",
            extra={
                "audio_storage_key": audio_storage_key,
                "timeout_seconds": self.timeout_seconds,
                "duration_seconds": duration_seconds,
            },
        )

        def _run() -> Any:
            return runner(audio_path)

        def _tick() -> None:
            self._emit("funasr_waiting")
            logger.info(
                "funasr_transcribe_waiting",
                extra={"audio_storage_key": audio_storage_key, "timeout_seconds": self.timeout_seconds},
            )

        if self.timeout_seconds and self.timeout_seconds > 0:
            raw = run_with_timeout(
                _run,
                timeout_seconds=float(self.timeout_seconds),
                on_tick=_tick,
                tick_seconds=float(self.heartbeat_seconds or DEFAULT_FUNASR_HEARTBEAT_SECONDS),
            )
        else:
            raw = _run()

        units = fit_funasr_units_to_duration(
            parse_funasr_generate_result(raw),
            duration_seconds=duration_seconds,
        )
        self._emit("funasr_finished")
        logger.info(
            "funasr_transcribe_finished",
            extra={
                "audio_storage_key": audio_storage_key,
                "unit_count": len(units),
                "duration_seconds": duration_seconds,
                "end_seconds": units[-1].end_seconds if units else None,
            },
        )
        return units


def _default_funasr_runner(audio_path: str) -> Any:
    try:
        from funasr import AutoModel  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("funasr_not_installed") from exc

    # Paraformer-zh with timestamp sentences — model download happens on first use.
    logger.info("funasr_automodel_loading", extra={"model": "paraformer-zh", "audio_path": audio_path})
    model = AutoModel(model="paraformer-zh", disable_update=True)
    logger.info("funasr_automodel_ready", extra={"model": "paraformer-zh"})
    return model.generate(input=audio_path)
