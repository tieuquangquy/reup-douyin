"""Safe, host-aware OmniVoice Studio engine catalog for Ops.

The Studio project exposes many engines, but they do not share one install or
synthesis API. This registry keeps display metadata and reviewed pip/source
recipes separate from adapter readiness so the web UI never implies that an
installed engine is also wired into production Preview/jobs.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OmniVoiceEngineSpec:
    id: str
    label: str
    probe_module: str | None
    install_mode: str  # builtin | pip | source | manual | external
    package: str | None = None
    install_command: str | None = None
    repo_url: str | None = None
    install_args: tuple[str, ...] = ()
    weights_repo_id: str | None = None
    weights_subdir: str = "weights"
    install_hint: str = ""
    adapter_ready: bool = False
    platforms: tuple[str, ...] = ("win32", "linux", "darwin")
    gpu_compat: tuple[str, ...] = ("cpu",)
    estimated_size_gb: float | None = None


@dataclass(frozen=True)
class OmniVoiceEngineInstall:
    engine_id: str
    strategy: str
    package: str | None = None
    install_command: str | None = None
    repo_url: str | None = None
    install_args: tuple[str, ...] = ()
    probe_module: str | None = None
    weights_repo_id: str | None = None
    weights_subdir: str = "weights"
    estimated_size_gb: float | None = None


OMNIVOICE_ENGINE_SPECS: tuple[OmniVoiceEngineSpec, ...] = (
    OmniVoiceEngineSpec(
        id="k2-fsa/OmniVoice",
        label="OmniVoice (600+ languages, zero-shot)",
        probe_module="omnivoice",
        install_mode="builtin",
        install_hint="Installed with the OmniVoice Studio base package; weights download on first use.",
        adapter_ready=True,
        gpu_compat=("cuda", "mps", "cpu"),
        estimated_size_gb=2.4,
    ),
    OmniVoiceEngineSpec(
        id="cosyvoice",
        label="CosyVoice 3 (zero-shot + instruct)",
        probe_module="cosyvoice",
        install_mode="source",
        repo_url="https://github.com/FunAudioLLM/CosyVoice.git",
        install_args=("-r", "requirements.txt"),
        install_hint="Clone FunAudioLLM/CosyVoice recursively, install its requirements and SoX.",
        gpu_compat=("cuda", "cpu"),
    ),
    OmniVoiceEngineSpec(
        id="gpt-sovits",
        label="GPT-SoVITS (external API server)",
        probe_module=None,
        install_mode="external",
        install_hint="Run GPT-SoVITS api_v2.py separately (normally port 9880).",
        gpu_compat=("cuda", "cpu"),
    ),
    OmniVoiceEngineSpec(
        id="voxcpm2",
        label="VoxCPM2 (30 languages, voice design)",
        probe_module="voxcpm",
        install_mode="pip",
        package="voxcpm",
        install_command="pip install voxcpm",
        install_hint="VoxCPM 2.0.3 or newer is recommended by OmniVoice Studio.",
        gpu_compat=("cuda", "mps", "cpu"),
    ),
    OmniVoiceEngineSpec(
        id="moss-tts-nano",
        label="MOSS-TTS-Nano (20 languages, CPU realtime)",
        probe_module="moss_tts",
        install_mode="source",
        repo_url="https://github.com/OpenMOSS/MOSS-TTS-Nano.git",
        install_args=("-e", "."),
        weights_repo_id="OpenMOSS-Team/MOSS-TTS-Nano-100M",
        install_hint="Clone OpenMOSS/MOSS-TTS-Nano and install it editable; it is not published on PyPI.",
        gpu_compat=("cuda", "cpu"),
        estimated_size_gb=0.4,
    ),
    OmniVoiceEngineSpec(
        id="kittentts",
        label="KittenTTS (English, CPU realtime)",
        probe_module="kittentts",
        install_mode="pip",
        package="kittentts",
        install_command="pip install kittentts",
        install_hint="Small ONNX CPU engine with preset voices.",
        estimated_size_gb=0.08,
    ),
    OmniVoiceEngineSpec(
        id="sherpa-onnx",
        label="Sherpa-ONNX (universal ONNX runtime)",
        probe_module="sherpa_onnx",
        install_mode="pip",
        package="sherpa-onnx",
        install_command="pip install sherpa-onnx",
        install_hint="Runtime install only; a compatible Sherpa TTS model directory is also required.",
        gpu_compat=("cuda", "cpu"),
    ),
    OmniVoiceEngineSpec(
        id="mlx-audio",
        label="MLX-Audio (Apple Silicon model family)",
        probe_module="mlx_audio",
        install_mode="pip",
        package="mlx-audio",
        install_command="pip install mlx-audio",
        install_hint="Apple Silicon only; offers Kokoro, CSM, Qwen3-TTS, Dia and other MLX models.",
        platforms=("darwin",),
        gpu_compat=("mps", "cpu"),
    ),
    OmniVoiceEngineSpec(
        id="indextts2",
        label="IndexTTS 2 (isolated sidecar)",
        probe_module="indextts.infer_v2",
        install_mode="source",
        repo_url="https://github.com/index-tts/index-tts.git",
        install_args=("-e", "."),
        weights_repo_id="IndexTeam/IndexTTS-2",
        weights_subdir="checkpoints",
        install_hint="Requires an isolated checkout, venv and IndexTeam/IndexTTS-2 weights (~12 GB total).",
        gpu_compat=("cuda",),
        estimated_size_gb=12.0,
    ),
    OmniVoiceEngineSpec(
        id="omnivoice-gguf",
        label="OmniVoice GGUF (CPU)",
        probe_module=None,
        install_mode="manual",
        install_hint="Requires the OmniVoice Studio C++ binary and GGUF quant weights.",
        estimated_size_gb=2.4,
    ),
    OmniVoiceEngineSpec(
        id="supertonic3",
        label="Supertonic 3 (31 languages, CPU ONNX)",
        probe_module="supertonic",
        install_mode="manual",
        install_hint="Install OmniVoice Studio's supertonic extra; model weights download on first use.",
        estimated_size_gb=0.4,
    ),
    OmniVoiceEngineSpec(
        id="moss-tts-v15",
        label="MOSS-TTS v1.5 (8B)",
        probe_module=None,
        install_mode="source",
        repo_url="https://github.com/OpenMOSS/MOSS-TTS.git",
        install_args=("-e", "."),
        install_hint="Clone OpenMOSS/MOSS-TTS into an isolated venv; approximately 16 GB of weights.",
        gpu_compat=("cuda", "cpu"),
        estimated_size_gb=16.0,
    ),
    OmniVoiceEngineSpec(
        id="dots-tts",
        label="dots.tts (2B)",
        probe_module=None,
        install_mode="source",
        repo_url="https://github.com/rednote-hilab/dots.tts.git",
        install_args=("-e", "."),
        install_hint="Clone rednote-hilab/dots.tts into an isolated venv; Windows is not supported upstream.",
        platforms=("linux", "darwin"),
        gpu_compat=("cuda", "cpu"),
        estimated_size_gb=9.0,
    ),
    OmniVoiceEngineSpec(
        id="confucius4-tts",
        label="Confucius4-TTS (cross-lingual clone)",
        probe_module=None,
        install_mode="source",
        repo_url="https://github.com/netease-youdao/Confucius4-TTS.git",
        install_args=("-e", "."),
        install_hint="Clone netease-youdao/Confucius4-TTS and create its Python 3.10 isolated venv.",
        gpu_compat=("cuda", "cpu"),
        estimated_size_gb=5.0,
    ),
)


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _platform_name(raw: str | None = None) -> str:
    value = (raw or sys.platform).lower()
    if value.startswith("win"):
        return "win32"
    if value.startswith("darwin"):
        return "darwin"
    return "linux" if value.startswith("linux") else value


def discover_omnivoice_engines(
    *,
    platform: str | None = None,
    module_available: Callable[[str], bool] | None = None,
    managed_installed: Callable[[str], bool] | None = None,
) -> list[dict[str, object]]:
    current_platform = _platform_name(platform)
    probe = module_available or _module_available
    managed_probe = managed_installed or (lambda _engine_id: False)
    result: list[dict[str, object]] = []

    for spec in OMNIVOICE_ENGINE_SPECS:
        compatible = current_platform in spec.platforms
        dependency_available = bool(
            (spec.probe_module and probe(spec.probe_module)) or managed_probe(spec.id)
        )
        if not compatible:
            dependency_status = "incompatible"
        elif spec.adapter_ready and dependency_available:
            dependency_status = "ready"
        elif dependency_available:
            dependency_status = "installed"
        elif spec.install_mode in {"builtin", "pip", "source"}:
            dependency_status = "missing"
        else:
            dependency_status = spec.install_mode

        installable = bool(
            compatible
            and spec.install_mode in {"pip", "source"}
            and (spec.install_command or spec.repo_url)
            and not dependency_available
        )
        selectable = bool(spec.adapter_ready and dependency_available and compatible)
        result.append(
            {
                "id": spec.id,
                "label": spec.label,
                "adapter_status": "ready" if spec.adapter_ready else "planned",
                "dependency_status": dependency_status,
                "selectable": selectable,
                "installable": installable,
                "install_mode": spec.install_mode,
                "install_command": (
                    spec.install_command
                    if installable and spec.install_command
                    else f"Managed source install: {spec.repo_url}"
                    if installable and spec.repo_url
                    else None
                ),
                "install_hint": spec.install_hint,
                "platforms": list(spec.platforms),
                "gpu_compat": list(spec.gpu_compat),
                "estimated_size_gb": spec.estimated_size_gb,
            }
        )
    return result


def get_omnivoice_engine_install(
    engine_id: str,
    *,
    platform: str | None = None,
) -> OmniVoiceEngineInstall | None:
    current_platform = _platform_name(platform)
    normalized = (engine_id or "").strip().lower()
    for spec in OMNIVOICE_ENGINE_SPECS:
        if spec.id.lower() != normalized:
            continue
        if (
            current_platform not in spec.platforms
            or spec.install_mode not in {"pip", "source"}
            or (spec.install_mode == "pip" and (not spec.package or not spec.install_command))
            or (spec.install_mode == "source" and not spec.repo_url)
        ):
            return None
        return OmniVoiceEngineInstall(
            engine_id=spec.id,
            strategy=spec.install_mode,
            package=spec.package,
            install_command=spec.install_command,
            repo_url=spec.repo_url,
            install_args=spec.install_args,
            probe_module=spec.probe_module,
            weights_repo_id=spec.weights_repo_id,
            weights_subdir=spec.weights_subdir,
            estimated_size_gb=spec.estimated_size_gb,
        )
    return None
