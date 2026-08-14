"""Expressive Gemini TTS adapter over the safe universal HTTP transport.

The endpoint/schema remains operator-configurable because Google Gemini TTS
deployments can differ (AI Studio, Vertex, or a compatible gateway).  The
adapter's responsibility is to require the expressive placeholders and prevent
silent downgrade to plain text.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import re
import threading
import time
import wave

from src.audio_pipeline.speech_budget import count_spoken_units
from src.tts_pipeline.catalog import normalize_gemini_voice_id
from src.tts_pipeline.http_connector import GenericHttpTtsProvider, HttpConnectorConfigError
from src.tts_pipeline.services.provider_audio_normalizer import canonicalize_provider_audio
from src.tts_pipeline.services.prosody_audio_qa import analyze_prosody_audio
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput


GEMINI_ADAPTER_VERSION = "gemini-expressive-http-adapter-v2"
GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL_ID = "gemini-2.5-flash-preview-tts"
VERTEX_GEMINI_DEFAULT_LOCATION = "us-central1"


def vertex_gemini_base_url(*, project_id: str, location: str = VERTEX_GEMINI_DEFAULT_LOCATION) -> str:
    """Return the Vertex AI publisher base URL for Gemini generateContent.

    The project and region are part of the endpoint so OAuth credentials and
    quota are unambiguously charged to the configured Cloud project.  The
    model path itself remains declarative in the HTTP connector manifest.
    """

    project = str(project_id or "").strip()
    region = str(location or VERTEX_GEMINI_DEFAULT_LOCATION).strip().lower()
    if not project or any(char in project for char in "/\\?#%\r\n\0"):
        raise ValueError("vertex_project_id_required")
    if not re.fullmatch(r"[a-z0-9-]{1,63}", region):
        raise ValueError("vertex_location_invalid")
    return f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google"


def default_vertex_gemini_http_connector_options(
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the OAuth-authenticated Vertex variant of the Gemini manifest."""

    output = default_gemini_http_connector_options(options)
    connector = dict(output.get("http_connector") or {})
    connector["auth"] = {
        "type": "bearer",
        "header_name": "Authorization",
        "prefix": "Bearer ",
        "test_method": "GET",
        # Vertex does not expose the AI Studio ``/models`` catalog under this
        # publisher base.  Keep the probe path static; synthesis still binds
        # the configured model in its declarative request path.
        "test_path": "/",
    }
    output["http_connector"] = connector
    return output


def default_gemini_http_connector_options(options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a safe AI Studio/compatible expressive mapping when none is supplied."""
    output = deepcopy(dict(options or {}))
    connector = output.get("http_connector")
    if not isinstance(connector, dict):
        connector = {}
    connector.setdefault("version", 1)
    connector.setdefault("mode", "custom")
    connector.setdefault(
        "auth",
        {
            "type": "query",
            "query_name": "key",
            "test_method": "GET",
            "test_path": "/models",
        },
    )
    connector.setdefault(
        "synthesis",
        {
            "path": "/models/{{model_id}}:generateContent",
            "method": "POST",
            "content_type": "application/json",
            "body": {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "{{voice_direction}}\\n"
                                    "Sample context: {{sample_context}}\\n"
                                    "Transcript:\\n{{rendered_text}}"
                                )
                            }
                        ],
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": "{{voice_id}}"}
                        }
                    },
                },
            },
            "response": {
                "type": "json_base64",
                "audio_path": "candidates[0].content.parts[0].inlineData.data",
                "mime_type_path": "candidates[0].content.parts[0].inlineData.mimeType",
            },
        },
    )
    output["http_connector"] = connector
    expressive = output.get("expressive_tts")
    if not isinstance(expressive, dict):
        expressive = {}
    expressive.setdefault("mode", "required")
    expressive.setdefault("min_chunk_seconds", 4.0)
    expressive.setdefault("max_chunk_seconds", 8.0)
    expressive.setdefault("max_concurrency", 1)
    expressive.setdefault("max_tempo_correction", 1.08)
    expressive.setdefault("max_review_atempo", 1.10)
    expressive.setdefault("min_request_interval_seconds", 0.0)
    expressive.setdefault("regenerate_on_timing_mismatch", False)
    expressive.setdefault("single_voice_mode", "required")
    expressive.setdefault("regenerate_on_emotion_mismatch", False)
    expressive.setdefault("synthesis_strategy", "whole_video")
    expressive.setdefault("max_whole_video_seconds", 180.0)
    expressive.setdefault("max_block_seconds", 45.0)
    expressive.setdefault("max_request_chars", 6000)
    expressive.setdefault("compact_trigger_ratio", 0.88)
    output["expressive_tts"] = expressive
    return output


class GeminiTtsProvider(GenericHttpTtsProvider):
    provider_name = "google_gemini"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_id: str,
        options: Mapping[str, Any],
        timeout_seconds: float,
        opener=None,
        resolver=None,
        monotonic=None,
        sleeper=None,
    ) -> None:
        effective_options = default_gemini_http_connector_options(options)
        expressive = effective_options.get("expressive_tts")
        self.expressive_options = dict(expressive) if isinstance(expressive, Mapping) else {}
        self.pcm_endianness = str(
            self.expressive_options.get("pcm_endianness") or "little"
        ).strip().lower()
        self._clock = monotonic or time.monotonic
        self._sleep = sleeper or time.sleep
        self._request_rate_lock = threading.Lock()
        self._next_request_at = 0.0
        super().__init__(
            provider_name="google_gemini",
            base_url=base_url,
            api_key=api_key,
            model_id=model_id or GEMINI_DEFAULT_MODEL_ID,
            options=effective_options,
            timeout_seconds=timeout_seconds,
            **({"opener": opener} if opener is not None else {}),
            **({"resolver": resolver} if resolver is not None else {}),
            **({"monotonic": monotonic} if monotonic is not None else {}),
            **({"sleeper": sleeper} if sleeper is not None else {}),
        )
        synthesis = self.manifest.synthesis
        if synthesis is None:
            raise HttpConnectorConfigError("Gemini expressive synthesis mapping is required")

        # Require at least one expressive execution field. A model configured
        # as Gemini must never silently run as a plain-text provider.
        placeholders = _placeholders(synthesis.body)
        if not placeholders.intersection(
            {"audio_tags", "rendered_text", "voice_direction", "sample_context", "ssml_text"}
        ):
            raise HttpConnectorConfigError(
                "Gemini synthesis mapping must consume audio_tags, rendered_text, "
                "voice_direction, sample_context, or ssml_text"
            )

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        requested_voice_id = str(request.voice_config.voice_id or "").strip()
        resolved_voice_id = normalize_gemini_voice_id(requested_voice_id or "Kore")
        if not resolved_voice_id:
            raise HttpConnectorConfigError(
                f"Unsupported Gemini voice id: {requested_voice_id[:120]}"
            )
        expressive_request = replace(
            request,
            voice_config=replace(request.voice_config, voice_id=resolved_voice_id),
        )
        if request.requested_features:
            expressive_request = replace(expressive_request, expressive_mode="required")
        single_voice_mode = str(
            self.expressive_options.get("single_voice_mode") or "off"
        ).strip().lower()
        if single_voice_mode == "required":
            # One request is the only strong guarantee that Gemini keeps one
            # narrator identity.  Splitting and joining independent model
            # calls can drift timbre even when voiceName is identical.
            chunks = [str(expressive_request.text or "").strip()]
        else:
            chunks = _semantic_chunks(
                expressive_request.text,
                min_seconds=_bounded_float(self.expressive_options.get("min_chunk_seconds"), 2.0, 8.0, 4.0),
                max_seconds=_bounded_float(self.expressive_options.get("max_chunk_seconds"), 4.0, 12.0, 8.0),
            )
        total_units = max(1, sum(max(1, count_spoken_units(chunk)) for chunk in chunks))

        def synthesize_chunk(item: tuple[int, str]) -> tuple[int, TtsProviderOutput, dict, TtsProviderInput]:
            index, chunk_text = item
            units = max(1, count_spoken_units(chunk_text))
            target = (
                float(expressive_request.target_duration_seconds or 0.0) * units / total_units
                if expressive_request.target_duration_seconds
                else None
            )
            direction = (
                f"{expressive_request.voice_direction or ''} "
                f"Performance chunk {index + 1} of {len(chunks)}. "
                "Preserve the emotion tags and continue naturally from the stated prosody state."
            ).strip()
            if single_voice_mode == "required":
                duration_direction = ""
                if target and target > 0:
                    duration_direction = (
                        f" Complete the entire narration naturally within {max(0.5, target * 0.98):.2f} "
                        f"to {target:.2f} seconds; use a consistently brisk pace and do not add "
                        "unwritten commentary or long pauses."
                    )
                direction = (
                    "Use exactly one narrator identity for the entire video: preserve the same "
                    "vocal timbre, age, accent, microphone character and speaking persona. "
                    "Do not change speaker identity."
                    + duration_direction
                    + " "
                    + direction
                ).strip()
            chunk_request = replace(
                expressive_request,
                text=chunk_text,
                voice_direction=direction,
                target_duration_seconds=target,
                performance_chunk_id=(
                    f"{expressive_request.performance_chunk_id}:{index + 1}"
                    if expressive_request.performance_chunk_id
                    else f"gemini-chunk-{index + 1}"
                ),
            )
            first = self._synthesize_once(chunk_request)
            first = _canonical_output(first, pcm_endianness=self.pcm_endianness)
            selected = first
            retried = False
            if (
                target
                and single_voice_mode != "required"
                and bool(self.expressive_options.get("regenerate_on_timing_mismatch", True))
                and float(first.duration_seconds) / max(0.1, target) > 1.08
            ):
                ratio = float(first.duration_seconds) / max(0.1, target)
                corrected = self._synthesize_once(
                    replace(
                        chunk_request,
                        voice_direction=(
                            f"{direction} Delivery correction: speak approximately "
                            f"{min(25, max(5, round((ratio - 1.0) * 100)))} percent faster, "
                            "while preserving the same emotion and natural articulation."
                        ),
                    )
                )
                corrected = _canonical_output(corrected, pcm_endianness=self.pcm_endianness)
                retried = True
                if abs(float(corrected.duration_seconds) - target) < abs(
                    float(first.duration_seconds) - target
                ):
                    selected = corrected
            return index, selected, {
                "chunk_index": index,
                "spoken_units": units,
                "target_duration_seconds": round(float(target or 0.0), 6) or None,
                "duration_seconds": round(float(selected.duration_seconds), 6),
                "timing_retry": retried,
                "emotion_retry": False,
                "planned_emotion": _tagged_emotion(chunk_text),
                "performance_chunk_id": chunk_request.performance_chunk_id,
            }, chunk_request

        max_workers = int(
            _bounded_float(self.expressive_options.get("max_concurrency"), 1.0, 4.0, 2.0)
        )
        with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as executor:
            results = list(executor.map(synthesize_chunk, enumerate(chunks)))
        results.sort(key=lambda item: item[0])
        outputs = [item[1] for item in results]
        chunk_reports = [item[2] for item in results]
        chunk_requests = [item[3] for item in results]
        for report, output in zip(chunk_reports, outputs, strict=True):
            report["audio_observables"] = _audio_observables(output)

        if single_voice_mode != "required" and bool(
            self.expressive_options.get("regenerate_on_emotion_mismatch", True)
        ):
            neutral_metrics = [
                dict(report.get("audio_observables") or {})
                for report in chunk_reports
                if report.get("planned_emotion") == "neutral"
            ]
            if neutral_metrics:
                neutral_rms = sum(float(row.get("rms_dbfs") or -60.0) for row in neutral_metrics) / len(neutral_metrics)
                neutral_zcr = sum(float(row.get("zero_crossing_rate_per_second") or 0.0) for row in neutral_metrics) / len(neutral_metrics)
                for index, report in enumerate(chunk_reports):
                    if report.get("planned_emotion") not in {"excited", "positive"}:
                        continue
                    metrics = dict(report.get("audio_observables") or {})
                    if _excited_observable(metrics, neutral_rms=neutral_rms, neutral_zcr=neutral_zcr):
                        report["emotion_qa"] = "passed_relative_to_neutral"
                        continue
                    stronger_request = replace(
                        chunk_requests[index],
                        voice_direction=(
                            f"{chunk_requests[index].voice_direction or ''} "
                            "Emotion correction: make the excitement unmistakable but natural; "
                            "increase vocal energy, pitch variation and lively pace."
                        ).strip(),
                    )
                    stronger = _canonical_output(
                        self._synthesize_once(stronger_request),
                        pcm_endianness=self.pcm_endianness,
                    )
                    stronger_metrics = _audio_observables(stronger)
                    report["emotion_retry"] = True
                    if _excited_score(stronger_metrics, neutral_rms, neutral_zcr) > _excited_score(
                        metrics, neutral_rms, neutral_zcr
                    ):
                        outputs[index] = stronger
                        report["audio_observables"] = stronger_metrics
                        report["duration_seconds"] = round(float(stronger.duration_seconds), 6)
                    report["emotion_qa"] = (
                        "passed_after_selective_retry"
                        if _excited_observable(
                            dict(report.get("audio_observables") or {}),
                            neutral_rms=neutral_rms,
                            neutral_zcr=neutral_zcr,
                        )
                        else "review_recommended_after_retry"
                    )
        joined_audio, joined_duration = _join_wav_outputs(outputs)
        warnings = list(
            dict.fromkeys(
                warning for output in outputs for warning in list(output.warnings or [])
            )
        )
        if any(bool(row["timing_retry"]) for row in chunk_reports):
            warnings.append("gemini_selective_chunk_timing_retry")
        if any(bool(row["emotion_retry"]) for row in chunk_reports):
            warnings.append("gemini_selective_chunk_emotion_retry")
        if any(row.get("emotion_qa") == "review_recommended_after_retry" for row in chunk_reports):
            warnings.append("gemini_chunk_emotion_review_recommended")
        contracts = [
            dict(dict(output.provider_metadata or {}).get("execution_contract") or {})
            for output in outputs
        ]
        applied = sorted(
            {
                feature
                for contract in contracts
                for feature in list(contract.get("applied_features") or [])
            }
        )
        degraded = sorted(
            {
                feature
                for contract in contracts
                for feature in list(contract.get("degraded_features") or [])
            }
        )
        output = TtsProviderOutput(
            audio_bytes=joined_audio,
            duration_seconds=joined_duration,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={
                **dict(outputs[0].provider_metadata or {}),
                "execution_contract": {
                    "schema_version": "tts-provider-execution-contract-v1",
                    "expressive_mode": "required",
                    "requested_features": list(expressive_request.requested_features),
                    "applied_features": applied,
                    "degraded_features": degraded,
                    "semantic_chunk_count": len(chunks),
                    "single_voice_mode": single_voice_mode,
                },
                "semantic_chunks": chunk_reports,
                "provider_http_call_count": len(chunks)
                + sum(1 for row in chunk_reports if row["timing_retry"])
                + sum(1 for row in chunk_reports if row["emotion_retry"]),
            },
            warnings=warnings,
        )
        return replace(
            output,
            provider_metadata={
                **dict(output.provider_metadata or {}),
                "adapter": GEMINI_ADAPTER_VERSION,
                "expressive_execution_required": bool(request.requested_features),
                "requested_voice_id": requested_voice_id,
                "resolved_voice_id": resolved_voice_id,
            },
        )

    def _synthesize_once(self, request: TtsProviderInput) -> TtsProviderOutput:
        """Serialize and pace Vertex/AI Studio calls under provider quotas."""

        try:
            interval = float(self.expressive_options.get("min_request_interval_seconds", 0.0))
        except (TypeError, ValueError):
            interval = 0.0
        interval = max(0.0, min(120.0, interval))
        with self._request_rate_lock:
            now = float(self._clock())
            wait_seconds = max(0.0, self._next_request_at - now)
            if wait_seconds > 0:
                self._sleep(wait_seconds)
            try:
                return super(GeminiTtsProvider, self).synthesize(request)
            finally:
                self._next_request_at = max(float(self._clock()), now) + interval


def _semantic_chunks(text: str, *, min_seconds: float, max_seconds: float) -> list[str]:
    """Group tagged clauses into 4-8 second expressive requests."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    blocks: list[str] = []
    pending_tag = ""
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            pending_tag = line
            continue
        blocks.append(f"{pending_tag}\n{line}".strip())
        pending_tag = ""
    if not blocks:
        blocks = [
            part.strip()
            for part in re.split(r"(?<=[.!?;:\u2026])\s+", str(text or ""))
            if part.strip()
        ]
    if not blocks:
        return [str(text or "").strip()]
    units_per_second = 4.5
    min_units = max(1, round(min_seconds * units_per_second))
    max_units = max(min_units, round(max_seconds * units_per_second))
    output: list[str] = []
    current: list[str] = []
    current_units = 0
    for block in blocks:
        block_units = max(1, count_spoken_units(block))
        if current and current_units >= min_units and current_units + block_units > max_units:
            output.append("\n".join(current))
            current = []
            current_units = 0
        current.append(block)
        current_units += block_units
    if current:
        if output and current_units < min_units:
            output[-1] = output[-1] + "\n" + "\n".join(current)
        else:
            output.append("\n".join(current))
    return output


def _canonical_output(
    output: TtsProviderOutput,
    *,
    pcm_endianness: str = "little",
) -> TtsProviderOutput:
    raw_mime = str(
        dict(output.provider_metadata or {}).get("response_mime_type")
        or output.mime_type
        or ""
    )
    content = output.audio_bytes
    if raw_mime.lower().startswith(("audio/l16", "audio/pcm")) and not content.startswith(b"RIFF"):
        content = _wrap_pcm_wav(
            content,
            mime_type=raw_mime,
            endianness=pcm_endianness,
        )
    audio, duration, normalization = canonicalize_provider_audio(
        content,
        mime_type="audio/wav" if content.startswith(b"RIFF") else output.mime_type,
        file_extension="wav" if content.startswith(b"RIFF") else output.file_extension,
    )
    return replace(
        output,
        audio_bytes=audio,
        duration_seconds=duration,
        mime_type="audio/wav",
        file_extension="wav",
        provider_metadata={
            **dict(output.provider_metadata or {}),
            "gemini_chunk_audio_normalization": normalization,
        },
    )


def _wrap_pcm_wav(content: bytes, *, mime_type: str, endianness: str) -> bytes:
    rate_match = re.search(r"(?:rate|sample_rate)\s*=\s*(\d+)", mime_type, re.IGNORECASE)
    sample_rate = int(rate_match.group(1)) if rate_match else 24000
    frames = bytes(content)
    if endianness == "big":
        swapped = bytearray(frames)
        for index in range(0, len(swapped) - 1, 2):
            swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
        frames = bytes(swapped)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(max(8000, min(sample_rate, 96000)))
        handle.writeframes(frames[: len(frames) - (len(frames) % 2)])
    return buffer.getvalue()


def _join_wav_outputs(outputs: list[TtsProviderOutput]) -> tuple[bytes, float]:
    params = None
    frames: list[bytes] = []
    total_frames = 0
    frame_rate = 48000
    for output in outputs:
        with wave.open(BytesIO(output.audio_bytes), "rb") as handle:
            current = (
                handle.getnchannels(),
                handle.getsampwidth(),
                handle.getframerate(),
            )
            if params is None:
                params = current
                frame_rate = current[2]
            elif current != params:
                raise HttpConnectorConfigError("Gemini chunk audio formats do not match")
            count = handle.getnframes()
            total_frames += count
            frames.append(handle.readframes(count))
    assert params is not None
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(params[0])
        output.setsampwidth(params[1])
        output.setframerate(params[2])
        output.writeframes(b"".join(frames))
    return buffer.getvalue(), total_frames / float(max(1, frame_rate))


def _bounded_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _tagged_emotion(text: str) -> str:
    tags = " ".join(re.findall(r"\[([^\]]+)\]", str(text or ""))).casefold()
    for emotion in ("excited", "positive", "serious", "curious", "reflective"):
        if emotion in tags:
            return emotion
    return "neutral"


def _audio_observables(output: TtsProviderOutput) -> dict[str, float | None]:
    report = analyze_prosody_audio(
        output.audio_bytes,
        prosody=None,
        provider_metadata=output.provider_metadata,
    )
    return {
        "rms_dbfs": report.get("rms_dbfs"),
        "zero_crossing_rate_per_second": report.get("zero_crossing_rate_per_second"),
        "duration_seconds": report.get("duration_seconds"),
    }


def _excited_observable(
    metrics: Mapping[str, Any],
    *,
    neutral_rms: float,
    neutral_zcr: float,
) -> bool:
    rms = float(metrics.get("rms_dbfs") or -60.0)
    zcr = float(metrics.get("zero_crossing_rate_per_second") or 0.0)
    return bool(rms >= neutral_rms + 0.5 or zcr >= neutral_zcr * 1.03)


def _excited_score(metrics: Mapping[str, Any], neutral_rms: float, neutral_zcr: float) -> float:
    rms = float(metrics.get("rms_dbfs") or -60.0)
    zcr = float(metrics.get("zero_crossing_rate_per_second") or 0.0)
    zcr_gain = (zcr / neutral_zcr - 1.0) * 20.0 if neutral_zcr > 0 else 0.0
    return (rms - neutral_rms) + zcr_gain


def _placeholders(value: Any) -> set[str]:
    import re

    pattern = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            found.update(match.group(1).lower() for match in pattern.finditer(node))
        elif isinstance(node, Mapping):
            for child in node.values():
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)
    return found
