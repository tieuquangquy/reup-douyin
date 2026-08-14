from types import SimpleNamespace
import base64
import json

from src.tts_pipeline.gemini_tts_provider import GeminiTtsProvider
from src.tts_pipeline.gemini_tts_provider import (
    default_gemini_http_connector_options,
    default_vertex_gemini_http_connector_options,
    vertex_gemini_base_url,
)
from src.tts_pipeline.gemini_tts_provider import _join_wav_outputs, _semantic_chunks, _wrap_pcm_wav
from src.tts_pipeline.types import TtsProviderOutput
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig
import io
import struct
import wave
from src.tts_pipeline.provider_factory import (
    ConfiguredButUnavailableTtsProvider,
    build_default_tts_provider,
)


def _config(body):
    return SimpleNamespace(
        provider="google_gemini",
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        options_json={
            "http_connector": {
                "synthesis": {
                    "path": "/models/{{model_id}}:generateContent",
                    "body": body,
                    "response": {
                        "type": "json_base64",
                        "audio_path": "audio",
                        "mime_type": "audio/wav",
                    },
                }
            }
        },
        voice_id="voice-1",
        speaking_rate=1.0,
        model_id="gemini-tts",
        local_backend="auto",
        device="auto",
        cli_binary="",
        timeout_seconds=30,
        fallback_provider="none",
        fallback_voice_id="",
        credential_mode="api_key",
        google_service_account_json=None,
        google_service_account_project_id="",
    )


def test_factory_builds_dedicated_gemini_expressive_adapter():
    provider = build_default_tts_provider(
        workspace_tts=_config(
            {
                "prompt": "{{voice_direction}}",
                "text": "{{rendered_text}}",
                "context": "{{sample_context}}",
            }
        ),
        allow_fallback=False,
    )
    assert isinstance(provider, GeminiTtsProvider), getattr(provider, "message", "")


def test_factory_rejects_gemini_manifest_that_drops_all_expressive_fields():
    provider = build_default_tts_provider(
        workspace_tts=_config({"text": "{{text}}"}),
        allow_fallback=False,
    )
    assert isinstance(provider, ConfiguredButUnavailableTtsProvider)


def test_default_gemini_mapping_uses_generate_content_audio_and_expressive_prompt():
    options = default_gemini_http_connector_options({})
    connector = options["http_connector"]
    synthesis = connector["synthesis"]
    prompt = synthesis["body"]["contents"][0]["parts"][0]["text"]
    assert synthesis["path"] == "/models/{{model_id}}:generateContent"
    assert synthesis["body"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert "{{voice_direction}}" in prompt
    assert "{{rendered_text}}" in prompt
    assert synthesis["response"]["audio_path"].endswith("inlineData.data")


def test_vertex_mapping_uses_bearer_auth_and_project_scoped_endpoint():
    options = default_vertex_gemini_http_connector_options({})
    assert options["http_connector"]["auth"]["type"] == "bearer"
    assert options["http_connector"]["synthesis"]["path"] == "/models/{{model_id}}:generateContent"
    assert vertex_gemini_base_url(
        project_id="paid-tts-project",
        location="us-central1",
    ) == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/paid-tts-project/"
        "locations/us-central1/publishers/google"
    )


def test_factory_builds_vertex_gemini_with_google_oauth(monkeypatch):
    cfg = _config({"text": "{{rendered_text}}", "direction": "{{voice_direction}}"})
    cfg.api_key = None
    cfg.base_url = ""
    cfg.options_json = {"vertex_ai": {"location": "asia-southeast1"}}
    cfg.credential_mode = "google_service_account"
    cfg.google_service_account_json = "validated-encrypted-boundary"
    cfg.google_service_account_project_id = "paid-tts-project"
    monkeypatch.setattr(
        "src.tts_pipeline.google_cloud_credentials.resolve_google_access_token",
        lambda **_kwargs: "oauth-token",
    )

    provider = build_default_tts_provider(workspace_tts=cfg, allow_fallback=False)

    assert isinstance(provider, GeminiTtsProvider), getattr(provider, "message", "")
    assert provider.base_url == (
        "https://asia-southeast1-aiplatform.googleapis.com/v1/projects/paid-tts-project/"
        "locations/asia-southeast1/publishers/google"
    )
    assert provider.manifest.auth.type == "bearer"


def test_semantic_chunker_preserves_inline_tags_and_splits_long_script():
    text = "\n".join(
        [
            "[neutral]",
            "Đây là phần mở đầu bình thường với một câu đầy đủ.",
            "[serious, slow]",
            "Nhưng điều quan trọng là chúng ta phải thật cẩn thận.",
            "[excited]",
            "Cuối cùng kết quả đã thành công ngoài mong đợi!",
        ]
    )
    chunks = _semantic_chunks(text, min_seconds=2.0, max_seconds=4.0)
    assert len(chunks) >= 2
    assert "[neutral]" in chunks[0]
    assert "[excited]" in chunks[-1]
    assert "Đây là phần mở đầu" in "\n".join(chunks)


def _wav(frames: int, value: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(struct.pack("<" + "h" * frames, *([value] * frames)))
    return output.getvalue()


def test_join_wav_outputs_preserves_order_and_duration():
    outputs = [
        TtsProviderOutput(_wav(4800, 10), 0.1, "audio/wav", "wav", {}),
        TtsProviderOutput(_wav(9600, 20), 0.2, "audio/wav", "wav", {}),
    ]
    joined, duration = _join_wav_outputs(outputs)
    assert joined.startswith(b"RIFF")
    assert round(duration, 3) == 0.3


def test_wraps_gemini_l16_pcm_as_wav_with_declared_rate():
    raw = struct.pack("<hhhh", 10, 20, -10, -20)
    wrapped = _wrap_pcm_wav(raw, mime_type="audio/L16;rate=24000", endianness="little")
    with wave.open(io.BytesIO(wrapped), "rb") as handle:
        assert handle.getframerate() == 24000
        assert handle.getnframes() == 4


def test_gemini_provider_renders_expressive_request_and_joins_audio():
    seen = []
    audio = _wav(4800, 100)

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def getcode(self):
            return 200

        def read(self, size=-1):
            payload = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "data": base64.b64encode(audio).decode("ascii"),
                                        "mimeType": "audio/wav",
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
            raw = json.dumps(payload).encode("utf-8")
            return raw if size < 0 else raw[:size]

    def opener(request, *, timeout):
        seen.append(json.loads(request.data.decode("utf-8")))
        return Response()

    provider = GeminiTtsProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test-key",
        model_id="gemini-2.5-flash-preview-tts",
        options=default_gemini_http_connector_options({}),
        timeout_seconds=8,
        opener=opener,
        resolver=lambda *args, **kwargs: [(2, 1, 6, "", ("142.250.1.1", 443))],
    )
    output = provider.synthesize(
        TtsProviderInput(
            text="[excited]\nMình đã thành công!",
            language_code="vi",
            voice_config=VoiceConfig(voice_id="vi-VN-Chirp3-HD-Aoede"),
            target_duration_seconds=0.1,
            voice_direction="speak with genuine excitement",
            sample_context="warm opening",
            audio_tags=("excited",),
            requested_features=("emotion",),
            expressive_mode="required",
        )
    )
    assert seen
    prompt = seen[0]["contents"][0]["parts"][0]["text"]
    assert "genuine excitement" in prompt
    assert "[excited]" in prompt
    assert (
        seen[0]["generationConfig"]["speechConfig"]["voiceConfig"]
        ["prebuiltVoiceConfig"]["voiceName"]
    ) == "Aoede"
    assert output.mime_type == "audio/wav"
    assert output.provider_metadata["adapter"] == "gemini-expressive-http-adapter-v2"
    assert output.provider_metadata["requested_voice_id"] == "vi-VN-Chirp3-HD-Aoede"
    assert output.provider_metadata["resolved_voice_id"] == "Aoede"


def test_single_voice_mode_keeps_long_script_in_one_provider_request():
    seen = []
    audio = _wav(4800, 100)

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def getcode(self):
            return 200

        def read(self, size=-1):
            raw = json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "data": base64.b64encode(audio).decode("ascii"),
                                            "mimeType": "audio/wav",
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")
            return raw if size < 0 else raw[:size]

    def opener(request, *, timeout):
        seen.append(json.loads(request.data.decode("utf-8")))
        return Response()

    options = default_gemini_http_connector_options(
        {"expressive_tts": {"single_voice_mode": "required"}}
    )
    provider = GeminiTtsProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test-key",
        model_id="gemini-2.5-flash-tts",
        options=options,
        timeout_seconds=8,
        opener=opener,
        resolver=lambda *args, **kwargs: [(2, 1, 6, "", ("142.250.1.1", 443))],
    )
    output = provider.synthesize(
        TtsProviderInput(
            text=(
                "[neutral]\nÄÃ¢y lÃ  pháº§n má»Ÿ Ä‘áº§u ráº¥t dÃ i cá»§a video.\n"
                "[excited]\nVÃ  Ä‘Ã¢y lÃ  pháº§n káº¿t tháº­t há»©ng khá»Ÿi!"
            ),
            language_code="vi",
            voice_config=VoiceConfig(voice_id="Kore"),
            voice_direction="Keep exactly the same narrator identity and timbre.",
            audio_tags=("neutral", "excited"),
            requested_features=("emotion",),
            expressive_mode="required",
        )
    )

    assert len(seen) == 1
    contract = output.provider_metadata["execution_contract"]
    assert contract["semantic_chunk_count"] == 1
    assert contract["single_voice_mode"] == "required"
    assert output.provider_metadata["provider_http_call_count"] == 1
