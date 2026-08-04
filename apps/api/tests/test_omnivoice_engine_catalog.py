from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.operations import install_tts_ai_engine, list_tts_ai_engines
from src.schemas.operations import TtsAiEngineCatalogResponse, TtsAiEngineInstallRequest
from src.tts_pipeline.omnivoice_engine_catalog import (
    discover_omnivoice_engines,
    get_omnivoice_engine_install,
)


def test_catalog_lists_all_engines_but_only_wired_adapter_is_selectable():
    installed = {"omnivoice", "kittentts"}
    engines = discover_omnivoice_engines(
        platform="win32",
        module_available=lambda name: name in installed,
    )

    assert len(engines) == 14
    by_id = {engine["id"]: engine for engine in engines}

    assert by_id["k2-fsa/OmniVoice"]["selectable"] is True
    assert by_id["k2-fsa/OmniVoice"]["dependency_status"] == "ready"

    assert by_id["kittentts"]["dependency_status"] == "installed"
    assert by_id["kittentts"]["adapter_status"] == "planned"
    assert by_id["kittentts"]["selectable"] is False

    assert by_id["voxcpm2"]["dependency_status"] == "missing"
    assert by_id["voxcpm2"]["installable"] is True
    assert by_id["voxcpm2"]["install_command"] == "pip install voxcpm"

    assert by_id["mlx-audio"]["dependency_status"] == "incompatible"
    assert by_id["mlx-audio"]["installable"] is False
    assert by_id["dots-tts"]["dependency_status"] == "incompatible"


def test_install_recipe_is_registry_owned_and_rejects_manual_engine():
    recipe = get_omnivoice_engine_install("sherpa-onnx", platform="win32")
    assert recipe is not None
    assert recipe.package == "sherpa-onnx"
    assert recipe.install_command == "pip install sherpa-onnx"

    source_recipe = get_omnivoice_engine_install("cosyvoice", platform="win32")
    assert source_recipe is not None
    assert source_recipe.strategy == "source"
    assert source_recipe.repo_url == "https://github.com/FunAudioLLM/CosyVoice.git"
    assert source_recipe.install_args == ("-r", "requirements.txt")

    assert get_omnivoice_engine_install("omnivoice-gguf", platform="win32") is None
    assert get_omnivoice_engine_install("mlx-audio", platform="win32") is None
    assert get_omnivoice_engine_install("unknown", platform="win32") is None


def test_catalog_rows_match_the_public_api_contract():
    payload = TtsAiEngineCatalogResponse(
        engines=discover_omnivoice_engines(
            platform="win32",
            module_available=lambda name: name == "omnivoice",
        )
    )

    assert payload.provider == "omnivoice"
    assert payload.engines[0].id == "k2-fsa/OmniVoice"
    assert payload.engines[0].adapter_status == "ready"
    assert payload.engines[1].install_hint


def test_managed_install_marker_marks_dependency_installed_but_not_selectable():
    engines = discover_omnivoice_engines(
        platform="win32",
        module_available=lambda _name: False,
        managed_installed=lambda engine_id: engine_id == "cosyvoice",
    )
    cosyvoice = {engine["id"]: engine for engine in engines}["cosyvoice"]

    assert cosyvoice["dependency_status"] == "installed"
    assert cosyvoice["installable"] is False
    assert cosyvoice["selectable"] is False


def test_ops_engine_routes_list_catalog_and_refuse_non_allowlisted_install():
    response = list_tts_ai_engines(workspace_id=uuid4())
    assert len(response.engines) == 14

    with pytest.raises(HTTPException) as raised:
        install_tts_ai_engine(
            "omnivoice-gguf",
            TtsAiEngineInstallRequest(),
            workspace_id=uuid4(),
        )
    assert raised.value.status_code == 400
    assert "manual" in str(raised.value.detail).lower() or "gguf" in str(raised.value.detail).lower()


def test_ops_engine_install_route_starts_registry_source_recipe_without_browser_commands(monkeypatch):
    captured = {}

    def fake_start_engine_install(**kwargs):
        captured.update(kwargs)
        return {
            "engine_id": kwargs["recipe"].engine_id,
            "status": "running",
            "step": "queued",
            "progress": 0,
            "detail": "Install queued",
            "log_tail": "",
            "error": "",
            "started_at": 1.0,
            "finished_at": None,
        }

    monkeypatch.setattr("src.api.routes.operations.start_engine_install", fake_start_engine_install)

    response = install_tts_ai_engine(
        "cosyvoice",
        TtsAiEngineInstallRequest(force_reinstall=True),
        workspace_id=uuid4(),
    )

    assert response.engine_id == "cosyvoice"
    assert response.status == "running"
    assert captured["recipe"].repo_url == "https://github.com/FunAudioLLM/CosyVoice.git"
    assert captured["force_reinstall"] is True
