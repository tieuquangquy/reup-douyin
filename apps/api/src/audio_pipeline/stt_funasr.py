from __future__ import annotations

import logging
import hashlib
import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.audio_pipeline.model_manager import generate_funasr_killable, get_funasr_model
from src.audio_pipeline.demucs_runner import run_captured
from src.audio_pipeline.types import TranscriptionUnit

logger = logging.getLogger(__name__)

_CAPTION_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n])\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n；;])\s*")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[，、,])\s*")
# Soft cap so untimed FunASR blobs become speakable/translatable DialogueBeats.
MAX_UNTIMED_BEAT_CHARS = 48
WORD_TIMESTAMP_GAP_MS = 700.0
# This is an ASR payload safety bound only.  Translation-ready sentence boundaries
# are rebuilt later by semantic_dialogue_segmentation from the token timeline.
WORD_TIMESTAMP_MAX_BEAT_MS = 15_000.0

# First-time ModelScope paraformer download can take several minutes on slow links.
DEFAULT_FUNASR_TIMEOUT_SECONDS = 900.0
DEFAULT_FUNASR_HEARTBEAT_SECONDS = 15.0
DEFAULT_FUNASR_CHUNK_SECONDS = 60.0
DEFAULT_FUNASR_CHUNK_OVERLAP_SECONDS = 1.5


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


def _timestamped_item_units(item: dict[str, Any]) -> list[TranscriptionUnit]:
    """Recover dialogue beats from FunASR's word-level ``timestamp`` array.

    Paraformer may omit ``sentence_info`` while still returning an exact
    timestamp for every emitted token. Treating that payload as untimed maps a
    whole video onto one TTS slot, so narration plays at the start and the rest
    becomes silence. Split only at measured pauses (or a bounded beat length)
    and preserve the original token evidence for review.
    """

    raw_timestamps = item.get("timestamp")
    if not isinstance(raw_timestamps, list) or not raw_timestamps:
        return []
    timestamps: list[tuple[float, float]] = []
    for raw in raw_timestamps:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            return []
        try:
            start_ms = float(raw[0])
            end_ms = float(raw[1])
        except (TypeError, ValueError):
            return []
        if start_ms < 0 or end_ms <= start_ms:
            return []
        if timestamps and start_ms < timestamps[-1][0]:
            return []
        timestamps.append((start_ms, end_ms))

    text = str(item.get("text") or "").strip()
    tokens = [token for token in text.split() if token]
    if len(tokens) != len(timestamps):
        compact = re.sub(r"\s+", "", text)
        tokens = list(compact) if len(compact) == len(timestamps) else []
    if len(tokens) != len(timestamps):
        return []

    groups: list[tuple[int, int]] = []
    group_start = 0
    for index in range(1, len(tokens)):
        pause_ms = timestamps[index][0] - timestamps[index - 1][1]
        span_ms = timestamps[index - 1][1] - timestamps[group_start][0]
        punctuation_boundary = bool(re.search(r"[。！？.!?；;]$", tokens[index - 1]))
        if (
            pause_ms >= WORD_TIMESTAMP_GAP_MS
            or span_ms >= WORD_TIMESTAMP_MAX_BEAT_MS
            or punctuation_boundary
        ):
            groups.append((group_start, index))
            group_start = index
    groups.append((group_start, len(tokens)))

    compact_cjk_tokens = all(
        len(token) == 1 and bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", token))
        for token in tokens
    )
    units: list[TranscriptionUnit] = []
    for start_index, end_index in groups:
        beat_tokens = tokens[start_index:end_index]
        beat_text = "".join(beat_tokens) if compact_cjk_tokens else " ".join(beat_tokens)
        units.append(
            TranscriptionUnit(
                text=beat_text,
                start_seconds=round(timestamps[start_index][0] / 1000.0, 3),
                end_seconds=round(timestamps[end_index - 1][1] / 1000.0, 3),
                confidence=float(item.get("confidence") or 0.8),
                flags=["funasr", "funasr_word_timestamps"],
                raw_payload={
                    "provider": "funasr",
                    "word_timestamp_range": [start_index, end_index - 1],
                    "timestamps": [
                        list(value) for value in timestamps[start_index:end_index]
                    ],
                },
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
        timestamped_units = _timestamped_item_units(item)
        if timestamped_units:
            units.extend(timestamped_units)
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

    # Timed sentences are evidence.  Preserve valid beats and clamp only the
    # offending tail; a global scale would move every otherwise-correct beat.
    all_outside = all(float(unit.start_seconds) >= duration for unit in units)
    if not all_outside:
        fitted = []
        for unit in units:
            flags = list(unit.flags or [])
            if "duration_fit" not in flags:
                flags.append("duration_fit")
            start = max(0.0, min(duration - 0.05, float(unit.start_seconds)))
            end = max(start + 0.05, min(duration, float(unit.end_seconds)))
            if float(unit.end_seconds) > duration:
                if "duration_clamped" not in flags:
                    flags.append("duration_clamped")
            fitted.append(replace(unit, start_seconds=round(start, 3), end_seconds=round(end, 3), flags=flags))
        return fitted

    # If every timestamp is uniformly outside the media window, proportional
    # scaling is the only recoverable interpretation of the stale payload.
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
    Run an injected/local callable in a worker thread and abort waiting after
    ``timeout_seconds``.

    Optional ``on_tick`` fires while still waiting so callers can heartbeat job
    progress during test/injected runners. Production FunASR uses the
    killable process boundary in ``model_manager.generate_funasr_killable``;
    this thread helper remains for dependency-injected runners only.
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
    warmup_timeout_seconds: float = DEFAULT_FUNASR_TIMEOUT_SECONDS
    heartbeat_seconds: float = DEFAULT_FUNASR_HEARTBEAT_SECONDS
    on_lifecycle: LifecycleHook | None = None
    chunk_seconds: float = DEFAULT_FUNASR_CHUNK_SECONDS
    chunk_overlap_seconds: float = DEFAULT_FUNASR_CHUNK_OVERLAP_SECONDS
    model_name: str = "paraformer-zh"
    device: str = "auto"
    checkpoint_root: str | None = None
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

        if (
            self.funasr_runner is None
            and duration_seconds is not None
            and float(duration_seconds) > max(10.0, float(self.chunk_seconds or 0.0))
        ):
            units = self._transcribe_chunked_audio(
                Path(audio_path),
                duration_seconds=float(duration_seconds),
            )
            self._emit("funasr_finished")
            logger.info(
                "funasr_transcribe_finished",
                extra={
                    "audio_storage_key": audio_storage_key,
                    "unit_count": len(units),
                    "duration_seconds": duration_seconds,
                    "chunked": True,
                },
            )
            return units

        def _run() -> Any:
            return runner(audio_path)

        def _tick() -> None:
            self._emit("funasr_waiting")
            logger.info(
                "funasr_transcribe_waiting",
                extra={"audio_storage_key": audio_storage_key, "timeout_seconds": self.timeout_seconds},
            )

        if self.timeout_seconds and self.timeout_seconds > 0 and self.funasr_runner is None:
            raw = generate_funasr_killable(
                audio_path,
                model_name=self.model_name,
                device=self.device,
                timeout_seconds=float(self.timeout_seconds),
                warmup_timeout_seconds=float(self.warmup_timeout_seconds),
                on_tick=_tick,
                tick_seconds=float(self.heartbeat_seconds or DEFAULT_FUNASR_HEARTBEAT_SECONDS),
            )
        elif self.timeout_seconds and self.timeout_seconds > 0:
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

    def _transcribe_chunked_audio(
        self,
        audio_path: Path,
        *,
        duration_seconds: float,
    ) -> list[TranscriptionUnit]:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg_not_found_for_chunked_funasr")
        chunk_seconds = max(10.0, float(self.chunk_seconds or DEFAULT_FUNASR_CHUNK_SECONDS))
        overlap = max(0.0, min(chunk_seconds / 4.0, float(self.chunk_overlap_seconds or 0.0)))
        starts: list[float] = []
        cursor = 0.0
        while cursor < duration_seconds - 0.01:
            starts.append(cursor)
            end = min(duration_seconds, cursor + chunk_seconds)
            if end >= duration_seconds:
                break
            cursor = max(cursor + 0.1, end - overlap)

        cache_dir = self._chunk_cache_dir(audio_path)
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
        all_units: list[TranscriptionUnit] = []
        with tempfile.TemporaryDirectory(prefix="funasr_chunks_") as tmp:
            for index, start in enumerate(starts):
                length = min(chunk_seconds, duration_seconds - start)
                self._emit(f"funasr_chunk|{index + 1}|{len(starts)}")
                cached = self._read_chunk_checkpoint(cache_dir, index)
                if cached is not None:
                    chunk_units = cached
                else:
                    chunk_path = Path(tmp) / f"chunk_{index:04d}.wav"
                    completed = run_captured(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-ss",
                            f"{start:.3f}",
                            "-t",
                            f"{length:.3f}",
                            "-i",
                            str(audio_path),
                            "-vn",
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            str(chunk_path),
                        ]
                    )
                    if completed.returncode != 0 or not chunk_path.is_file():
                        detail = (completed.stderr or completed.stdout or "ffmpeg chunk failed").strip()
                        raise RuntimeError(detail[:500])
                    raw = generate_funasr_killable(
                        str(chunk_path),
                        model_name=self.model_name,
                        device=self.device,
                        timeout_seconds=float(self.timeout_seconds),
                        warmup_timeout_seconds=float(self.warmup_timeout_seconds),
                        on_tick=lambda: self._emit("funasr_waiting"),
                        tick_seconds=float(self.heartbeat_seconds or DEFAULT_FUNASR_HEARTBEAT_SECONDS),
                    )
                    local_units = fit_funasr_units_to_duration(
                        parse_funasr_generate_result(raw),
                        duration_seconds=length,
                    )
                    chunk_units = [
                        replace(
                            unit,
                            start_seconds=round(unit.start_seconds + start, 3),
                            end_seconds=round(min(duration_seconds, unit.end_seconds + start), 3),
                            flags=list(dict.fromkeys([*(unit.flags or []), "funasr_chunked"])),
                            raw_payload={
                                **(unit.raw_payload or {}),
                                "chunk_index": index,
                                "chunk_start_seconds": start,
                            },
                        )
                        for unit in local_units
                    ]
                    self._write_chunk_checkpoint(cache_dir, index, chunk_units)
                all_units.extend(chunk_units)
        return merge_chunked_units(all_units, overlap_seconds=overlap)

    def _chunk_cache_dir(self, audio_path: Path) -> Path | None:
        if not self.checkpoint_root:
            return None
        try:
            stat = audio_path.stat()
            identity = f"{audio_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{self.model_name}|{self.chunk_seconds}|{self.chunk_overlap_seconds}"
        except OSError:
            return None
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return Path(self.checkpoint_root) / digest

    @staticmethod
    def _read_chunk_checkpoint(cache_dir: Path | None, index: int) -> list[TranscriptionUnit] | None:
        if cache_dir is None:
            return None
        path = cache_dir / f"chunk_{index:04d}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [TranscriptionUnit(**row) for row in payload]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_chunk_checkpoint(
        cache_dir: Path | None,
        index: int,
        units: list[TranscriptionUnit],
    ) -> None:
        if cache_dir is None:
            return
        path = cache_dir / f"chunk_{index:04d}.json"
        temp = path.with_suffix(".json.part")
        payload = [
            {
                "text": unit.text,
                "start_seconds": unit.start_seconds,
                "end_seconds": unit.end_seconds,
                "confidence": unit.confidence,
                "speaker_label": unit.speaker_label,
                "flags": list(unit.flags or []),
                "raw_payload": unit.raw_payload,
            }
            for unit in units
        ]
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)


def merge_chunked_units(
    units: list[TranscriptionUnit],
    *,
    overlap_seconds: float,
) -> list[TranscriptionUnit]:
    """Stitch chunk overlap without duplicating partial boundary phrases.

    The old implementation only removed whole-unit equality.  Paraformer commonly
    emits ``...这样鼻`` at the end of one chunk and ``这样鼻影...`` at the start of
    the next, so exact-unit dedupe leaves both a timestamp overlap and duplicated
    speech.  Align suffix/prefix timed tokens and retain the higher-confidence copy.
    """
    ordered = sorted(units, key=lambda unit: (unit.start_seconds, unit.end_seconds))
    merged: list[TranscriptionUnit] = []
    for unit in ordered:
        text_key = re.sub(r"\s+", "", (unit.text or "").strip())
        duplicate = False
        for previous_index in range(len(merged) - 1, max(-1, len(merged) - 5), -1):
            previous = merged[previous_index]
            previous_key = re.sub(r"\s+", "", (previous.text or "").strip())
            temporal_overlap = min(previous.end_seconds, unit.end_seconds) - max(
                previous.start_seconds, unit.start_seconds
            )
            if text_key and text_key == previous_key and temporal_overlap >= -max(0.05, overlap_seconds):
                duplicate = True
                if (unit.confidence or 0.0) > (previous.confidence or 0.0):
                    merged[previous_index] = unit
                break
            if temporal_overlap < -0.1 or not _different_chunk(previous, unit):
                continue
            alignment = _timed_suffix_prefix_alignment(previous, unit)
            if alignment is None:
                continue
            previous_count, current_count, mode = alignment
            if (unit.confidence or 0.0) > (previous.confidence or 0.0) + 0.1:
                trimmed_previous = _trim_timed_unit_suffix(
                    previous,
                    previous_count,
                    mode=mode,
                )
                if trimmed_previous is None:
                    merged.pop(previous_index)
                else:
                    merged[previous_index] = trimmed_previous
                duplicate = False
            else:
                trimmed_current = _trim_timed_unit_prefix(
                    unit,
                    current_count,
                    mode=mode,
                )
                if trimmed_current is None:
                    duplicate = True
                else:
                    unit = trimmed_current
                    text_key = re.sub(r"\s+", "", (unit.text or "").strip())
                break
        if not duplicate:
            merged.append(unit)
    return sorted(merged, key=lambda unit: (unit.start_seconds, unit.end_seconds))


def _different_chunk(left: TranscriptionUnit, right: TranscriptionUnit) -> bool:
    left_raw = dict(left.raw_payload or {})
    right_raw = dict(right.raw_payload or {})
    left_chunk = left_raw.get("chunk_index")
    right_chunk = right_raw.get("chunk_index")
    return left_chunk is not None and right_chunk is not None and left_chunk != right_chunk


def _timed_suffix_prefix_alignment(
    left: TranscriptionUnit,
    right: TranscriptionUnit,
) -> tuple[int, int, str] | None:
    left_timed = _timed_unit_tokens(left)
    right_timed = _timed_unit_tokens(right)
    if left_timed is None or right_timed is None:
        return None
    left_tokens, _left_times = left_timed
    right_tokens, _right_times = right_timed
    left_window = min(24, len(left_tokens))
    right_window = min(24, len(right_tokens))
    best: tuple[float, int, int, str] | None = None
    for left_count in range(1, left_window + 1):
        left_text = re.sub(r"\s+", "", "".join(left_tokens[-left_count:]))
        if not left_text:
            continue
        for right_count in range(1, right_window + 1):
            right_text = re.sub(r"\s+", "", "".join(right_tokens[:right_count]))
            if not right_text:
                continue
            if left_text == right_text and len(left_text) >= 2:
                candidate = (1000.0 + len(left_text), left_count, right_count, "exact_suffix_prefix")
            elif min(len(left_text), len(right_text)) >= 4:
                ratio = SequenceMatcher(None, left_text, right_text).ratio()
                if ratio < 0.86:
                    continue
                candidate = (ratio * 100.0 + min(len(left_text), len(right_text)), left_count, right_count, "fuzzy_suffix_prefix")
            else:
                continue
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        return None
    return best[1], best[2], best[3]


def _timed_unit_tokens(
    unit: TranscriptionUnit,
) -> tuple[list[str], list[tuple[float, float]]] | None:
    raw = dict(unit.raw_payload or {})
    values = raw.get("timestamps")
    if not isinstance(values, list) or not values:
        return None
    timings: list[tuple[float, float]] = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            start_ms = float(value[0])
            end_ms = float(value[1])
        except (TypeError, ValueError):
            return None
        if start_ms < 0 or end_ms <= start_ms:
            return None
        timings.append((start_ms, end_ms))
    split = [piece for piece in str(unit.text or "").split() if piece]
    compact = re.sub(r"\s+", "", str(unit.text or ""))
    tokens = split if len(split) == len(timings) else list(compact) if len(compact) == len(timings) else []
    if len(tokens) != len(timings):
        return None
    if raw.get("timestamps_are_absolute") is not True:
        chunk_offset = max(0.0, float(raw.get("chunk_start_seconds") or 0.0) * 1000.0)
        first = timings[0][0]
        measured = float(unit.start_seconds) * 1000.0
        if abs((first + chunk_offset) - measured) + 1.0 < abs(first - measured):
            timings = [(start + chunk_offset, end + chunk_offset) for start, end in timings]
    return tokens, timings


def _trim_timed_unit_prefix(
    unit: TranscriptionUnit,
    count: int,
    *,
    mode: str,
) -> TranscriptionUnit | None:
    timed = _timed_unit_tokens(unit)
    if timed is None:
        return unit
    tokens, timestamps = timed
    if count <= 0:
        return unit
    if count >= len(tokens):
        return None
    return _rebuild_trimmed_timed_unit(
        unit,
        tokens[count:],
        timestamps[count:],
        removed_prefix=count,
        removed_suffix=0,
        mode=mode,
    )


def _trim_timed_unit_suffix(
    unit: TranscriptionUnit,
    count: int,
    *,
    mode: str,
) -> TranscriptionUnit | None:
    timed = _timed_unit_tokens(unit)
    if timed is None:
        return unit
    tokens, timestamps = timed
    if count <= 0:
        return unit
    if count >= len(tokens):
        return None
    return _rebuild_trimmed_timed_unit(
        unit,
        tokens[:-count],
        timestamps[:-count],
        removed_prefix=0,
        removed_suffix=count,
        mode=mode,
    )


def _rebuild_trimmed_timed_unit(
    unit: TranscriptionUnit,
    tokens: list[str],
    timestamps: list[tuple[float, float]],
    *,
    removed_prefix: int,
    removed_suffix: int,
    mode: str,
) -> TranscriptionUnit:
    raw = dict(unit.raw_payload or {})
    original_range = list(raw.get("word_timestamp_range") or [])
    range_start = int(original_range[0]) if len(original_range) >= 2 else 0
    range_end = int(original_range[1]) if len(original_range) >= 2 else range_start + len(tokens) - 1
    raw["timestamps"] = [[round(start, 3), round(end, 3)] for start, end in timestamps]
    raw["timestamps_are_absolute"] = True
    raw["word_timestamp_range"] = [
        range_start + removed_prefix,
        range_end - removed_suffix,
    ]
    raw["chunk_stitch"] = {
        "recipe_version": "funasr-chunk-stitch-v2",
        "mode": mode,
        "removed_prefix_tokens": removed_prefix,
        "removed_suffix_tokens": removed_suffix,
    }
    flags = list(dict.fromkeys([*(unit.flags or []), "funasr_chunk_overlap_aligned"]))
    compact_original = " " not in str(unit.text or "").strip()
    text = "".join(tokens) if compact_original else " ".join(tokens)
    return replace(
        unit,
        text=text,
        start_seconds=round(timestamps[0][0] / 1000.0, 3),
        end_seconds=round(timestamps[-1][1] / 1000.0, 3),
        flags=flags,
        raw_payload=raw,
    )


def _default_funasr_runner(audio_path: str) -> Any:
    try:
        import funasr  # noqa: F401  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("funasr_not_installed") from exc

    # Paraformer-zh with timestamp sentences — model download happens on first use.
    model = get_funasr_model("paraformer-zh")
    return model.generate(input=audio_path)
