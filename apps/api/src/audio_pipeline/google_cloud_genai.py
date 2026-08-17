"""Native Google Cloud Agent Platform client built on the Google Gen AI SDK."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

GOOGLE_CLOUD_PROVIDER = "google_cloud"
GOOGLE_CLOUD_DEFAULT_MODEL = "gemini-3.7-flash"
GOOGLE_CLOUD_DEFAULT_REGION = "global"
GOOGLE_CLOUD_FALLBACK_MODELS = (GOOGLE_CLOUD_DEFAULT_MODEL,)


def _load_google_genai() -> Any:
    try:
        from google import genai
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "google_cloud_sdk_missing: install the google-genai package"
        ) from exc
    return genai


def _safe_error_detail(exc: Exception, *, api_key: str) -> str:
    detail = str(exc or type(exc).__name__).strip() or type(exc).__name__
    if api_key:
        detail = detail.replace(api_key, "[REDACTED]")
    return detail[:400]


def _google_cloud_error_code(exc: Exception) -> str:
    raw = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        status = int(raw)
    except (TypeError, ValueError):
        match = re.search(r"\b([1-5]\d{2})\b", str(raw or exc))
        status = int(match.group(1)) if match else 0
    if 100 <= status <= 599:
        return f"google_cloud_http_{status}"
    return "google_cloud_request_failed"


def is_google_cloud_retryable_error(exc: BaseException) -> bool:
    detail = str(exc or "").casefold()
    match = re.search(r"google_cloud_http_(\d{3})", detail)
    if match:
        status = int(match.group(1))
        return status in {408, 409, 429} or status >= 500
    return "google_cloud_request_failed" in detail and any(
        marker in detail
        for marker in ("timeout", "timed out", "connection", "temporarily unavailable")
    )


def build_google_cloud_sdk_client(*, api_key: str, region: str, timeout_seconds: float) -> Any:
    if not api_key.strip():
        raise RuntimeError("google_cloud_api_key_missing")
    selected_region = (region or GOOGLE_CLOUD_DEFAULT_REGION).strip().lower()
    if selected_region != GOOGLE_CLOUD_DEFAULT_REGION:
        raise RuntimeError(
            "google_cloud_region_unsupported_for_api_key: use global"
        )
    genai = _load_google_genai()
    kwargs: dict[str, Any] = {
        "vertexai": True,
        "api_key": api_key.strip(),
    }
    # Google Cloud Agent Platform Express Mode API keys are global. The SDK
    # rejects api_key together with project/location as mutually exclusive.
    # google-genai uses milliseconds for HttpOptions.timeout. Keep this optional
    # for compatibility with SDK releases that do not expose HttpOptions yet.
    try:
        from google.genai import types

        kwargs["http_options"] = types.HttpOptions(
            timeout=max(1, int(float(timeout_seconds or 90.0) * 1000))
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    client = genai.Client(**kwargs)
    api_client = getattr(client, "_api_client", None)
    project = getattr(api_client, "project", None)
    location = getattr(api_client, "location", None)
    resolved_key = getattr(api_client, "api_key", None)
    http_options = getattr(api_client, "_http_options", None)
    base_url = str(getattr(http_options, "base_url", "") or "").rstrip("/")
    if project or location or not resolved_key or base_url != "https://aiplatform.googleapis.com":
        raise RuntimeError("google_cloud_api_key_routing_invalid")
    return client


def _extract_text(response: Any) -> str:
    direct = getattr(response, "text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, Sequence):
        candidates = []
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None)
        if not isinstance(parts, Sequence):
            continue
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


@dataclass
class GoogleCloudAgentPlatformClient:
    """Text completion client for dialogue translation and connection probes."""

    api_key: str
    model: str = GOOGLE_CLOUD_DEFAULT_MODEL
    region: str = GOOGLE_CLOUD_DEFAULT_REGION
    timeout_seconds: float = 90.0
    provider_name: str = GOOGLE_CLOUD_PROVIDER
    sdk_client: Any | None = field(default=None, repr=False)

    def _client(self) -> Any:
        if self.sdk_client is None:
            self.sdk_client = build_google_cloud_sdk_client(
                api_key=self.api_key,
                region=self.region,
                timeout_seconds=self.timeout_seconds,
            )
        return self.sdk_client

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        response_mime_type: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        model: str | None = None,
    ) -> str:
        if not self.api_key.strip():
            raise RuntimeError("google_cloud_api_key_missing")
        chosen_model = (model or self.model or GOOGLE_CLOUD_DEFAULT_MODEL).strip()
        if not chosen_model:
            raise RuntimeError("google_cloud_model_missing")
        config: dict[str, Any] = {
            "temperature": float(temperature),
            "max_output_tokens": int(max_output_tokens),
        }
        if system_instruction:
            config["system_instruction"] = system_instruction
        if response_mime_type:
            config["response_mime_type"] = response_mime_type
        try:
            response = self._client().models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 - normalize SDK failures for Ops/runtime
            raise RuntimeError(
                f"{_google_cloud_error_code(exc)}:{_safe_error_detail(exc, api_key=self.api_key)}"
            ) from exc
        text = _extract_text(response)
        if not text:
            raise RuntimeError("google_cloud_empty_response")
        return text

    def complete(self, prompt: str) -> str:
        return self.generate_text(prompt, temperature=0.2, max_output_tokens=4096)


class GoogleCloudCaptionChatAdapter:
    """Expose the tiny chat-completions surface used by the Caption pipeline.

    The transport is still the native Google Gen AI SDK. The compatibility
    surface only lets the existing provider-agnostic Caption orchestration keep
    its stable call contract.
    """

    def __init__(self, client: GoogleCloudAgentPlatformClient) -> None:
        self.native_client = client
        self.chat = SimpleNamespace(completions=self)

    def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        response_format: Mapping[str, Any] | None = None,
        temperature: float = 0.0,
        **_: Any,
    ) -> Any:
        system_parts: list[str] = []
        dialogue_parts: list[str] = []
        for message in messages:
            role = str(message.get("role") or "user").strip().lower()
            content = str(message.get("content") or "")
            if role == "system":
                system_parts.append(content)
            else:
                dialogue_parts.append(f"{role.upper()}:\n{content}")
        wants_json = bool(response_format and response_format.get("type") == "json_object")
        text = self.native_client.generate_text(
            "\n\n".join(dialogue_parts),
            system_instruction="\n\n".join(system_parts) or None,
            response_mime_type="application/json" if wants_json else None,
            temperature=temperature,
            model=model,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )


def build_google_cloud_caption_client(
    *, api_key: str, model: str, region: str, timeout_seconds: float
) -> GoogleCloudCaptionChatAdapter:
    return GoogleCloudCaptionChatAdapter(
        GoogleCloudAgentPlatformClient(
            api_key=api_key,
            model=model or GOOGLE_CLOUD_DEFAULT_MODEL,
            region=region or GOOGLE_CLOUD_DEFAULT_REGION,
            timeout_seconds=timeout_seconds,
        )
    )


def list_google_cloud_models(
    *, api_key: str, region: str, timeout_seconds: float
) -> list[str]:
    client = build_google_cloud_sdk_client(
        api_key=api_key,
        region=region,
        timeout_seconds=timeout_seconds,
    )
    models: list[str] = []
    try:
        rows = client.models.list()
        for item in rows:
            raw = str(getattr(item, "name", None) or getattr(item, "id", None) or "").strip()
            if not raw:
                continue
            name = re.sub(r"^.*?/models/", "", raw)
            if name.startswith("gemini-"):
                models.append(name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"{_google_cloud_error_code(exc)}:{_safe_error_detail(exc, api_key=api_key)}"
        ) from exc
    return models
