"""Native Agent Platform Express Mode TTS provider using google-genai."""

from __future__ import annotations

import base64
from dataclasses import replace
from typing import Any, Mapping, Sequence

from src.audio_pipeline.google_cloud_genai import (
    GOOGLE_CLOUD_DEFAULT_REGION,
    _google_cloud_error_code,
    _safe_error_detail,
    build_google_cloud_sdk_client,
)
from src.tts_pipeline.catalog import GOOGLE_CLOUD_AGENT_TTS_MODELS
from src.tts_pipeline.gemini_tts_provider import (
    GeminiTtsProvider,
)
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput

GOOGLE_CLOUD_TTS_PROVIDER = "google_cloud_tts"
GOOGLE_CLOUD_TTS_DEFAULT_MODEL = GOOGLE_CLOUD_AGENT_TTS_MODELS[0]
GOOGLE_CLOUD_TTS_ADAPTER_VERSION = "google-cloud-agent-tts-sdk-v1"


def _model_not_available(exc: BaseException) -> bool:
    detail = str(exc or "").casefold()
    return "google_cloud_http_404" in detail and (
        "publisher model" in detail or "not found" in detail
    )


def _audio_part(response: Any) -> tuple[bytes, str]:
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, Sequence):
        candidates = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None)
        if not isinstance(parts, Sequence):
            continue
        for part in parts:
            inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if inline is None:
                continue
            if isinstance(inline, Mapping):
                data = inline.get("data")
                mime_type = str(inline.get("mime_type") or inline.get("mimeType") or "")
            else:
                data = getattr(inline, "data", None)
                mime_type = str(
                    getattr(inline, "mime_type", None)
                    or getattr(inline, "mimeType", None)
                    or ""
                )
            if isinstance(data, str):
                try:
                    data = base64.b64decode(data, validate=True)
                except (ValueError, TypeError) as exc:
                    raise RuntimeError("google_cloud_tts_audio_base64_invalid") from exc
            if isinstance(data, (bytes, bytearray)) and data:
                return bytes(data), mime_type or "audio/L16;codec=pcm;rate=24000"
    raise RuntimeError("google_cloud_tts_empty_audio_response")


class GoogleCloudAgentTtsProvider(GeminiTtsProvider):
    """Reuse the proven expressive/single-voice orchestration with native transport."""

    provider_name = GOOGLE_CLOUD_TTS_PROVIDER

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
        region: str = GOOGLE_CLOUD_DEFAULT_REGION,
        options: Mapping[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        sdk_client: Any | None = None,
    ) -> None:
        if not str(api_key or "").strip():
            raise ValueError("google_cloud_tts_api_key_missing")
        selected_region = str(region or GOOGLE_CLOUD_DEFAULT_REGION).strip().lower()
        if selected_region != GOOGLE_CLOUD_DEFAULT_REGION:
            raise ValueError("google_cloud_tts_region_unsupported: use global")
        self._agent_api_key = str(api_key).strip()
        self.region = selected_region
        self._agent_sdk_client = sdk_client
        self._agent_timeout_seconds = float(timeout_seconds or 120.0)
        self._configured_model_id = str(model_id or GOOGLE_CLOUD_TTS_DEFAULT_MODEL).strip()
        self._resolved_model_id = ""
        agent_options = dict(dict(options or {}).get("google_cloud_tts") or {})
        self._model_fallback_enabled = bool(agent_options.get("model_fallback_on_not_found", True))
        super().__init__(
            base_url="https://aiplatform.googleapis.com",
            api_key=self._agent_api_key,
            model_id=model_id or GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
            options=dict(options or {}),
            timeout_seconds=timeout_seconds,
        )
        self.provider_name = GOOGLE_CLOUD_TTS_PROVIDER

    def _model_candidates(self) -> list[str]:
        primary = self._resolved_model_id or self._configured_model_id
        candidates = [primary]
        if self._model_fallback_enabled and not self._resolved_model_id:
            candidates.extend(GOOGLE_CLOUD_AGENT_TTS_MODELS)
        return list(dict.fromkeys(model for model in candidates if model))

    def _client(self) -> Any:
        if self._agent_sdk_client is None:
            self._agent_sdk_client = build_google_cloud_sdk_client(
                api_key=self._agent_api_key,
                region=self.region,
                timeout_seconds=self._agent_timeout_seconds,
            )
        return self._agent_sdk_client

    def _synthesize_once(self, request: TtsProviderInput) -> TtsProviderOutput:
        """Serialize SDK calls under the same quota pacing contract as Gemini HTTP."""

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
                return self._native_synthesize(request)
            finally:
                self._next_request_at = max(float(self._clock()), now) + interval

    def _native_synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        direction = str(request.voice_direction or "").strip()
        sample_context = str(request.sample_context or "").strip()
        prompt_parts = [
            direction,
            f"Sample context: {sample_context}" if sample_context else "",
            "Transcript:",
            str(request.text or "").strip(),
        ]
        prompt = "\n".join(part for part in prompt_parts if part)
        config = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": str(request.voice_config.voice_id or "Achernar")
                    }
                }
            },
        }
        candidates = self._model_candidates()
        attempted: list[str] = []
        selected_model = ""
        audio_bytes = b""
        mime_type = ""
        for index, candidate_model in enumerate(candidates):
            attempted.append(candidate_model)
            try:
                response = self._client().models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config=config,
                )
                audio_bytes, mime_type = _audio_part(response)
                selected_model = candidate_model
                self._resolved_model_id = candidate_model
                break
            except Exception as exc:  # noqa: BLE001 - normalize SDK errors for Ops and jobs
                if str(exc).startswith("google_cloud_tts_"):
                    normalized = exc
                else:
                    normalized = RuntimeError(
                        f"{_google_cloud_error_code(exc)}:"
                        f"{_safe_error_detail(exc, api_key=self._agent_api_key)}"
                    )
                has_fallback = index + 1 < len(candidates)
                if has_fallback and self._model_fallback_enabled and _model_not_available(normalized):
                    continue
                if normalized is exc:
                    raise
                raise normalized from exc
        if not selected_model or not audio_bytes:
            raise RuntimeError("google_cloud_tts_empty_audio_response")
        requested = list(request.requested_features)
        model_fallback_used = selected_model != self._configured_model_id
        warnings = []
        if model_fallback_used:
            warnings.append(
                f"google_cloud_tts_model_fallback:{self._configured_model_id}->{selected_model}"
            )
        output = TtsProviderOutput(
            audio_bytes=audio_bytes,
            duration_seconds=0.0,
            mime_type=mime_type,
            file_extension="wav",
            provider_metadata={
                "provider": GOOGLE_CLOUD_TTS_PROVIDER,
                "model_id": selected_model,
                "requested_model_id": self._configured_model_id,
                "resolved_model_id": selected_model,
                "model_fallback_used": model_fallback_used,
                "model_attempts": attempted,
                "region": self.region,
                "response_mime_type": mime_type,
                "execution_contract": {
                    "schema_version": "tts-provider-execution-contract-v1",
                    "expressive_mode": request.expressive_mode,
                    "requested_features": requested,
                    "applied_features": requested,
                    "degraded_features": [],
                },
            },
            warnings=warnings,
        )
        return output

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        output = super().synthesize(request)
        return replace(
            output,
            provider_metadata={
                **dict(output.provider_metadata or {}),
                "provider": GOOGLE_CLOUD_TTS_PROVIDER,
                "adapter": GOOGLE_CLOUD_TTS_ADAPTER_VERSION,
                "region": self.region,
            },
        )
