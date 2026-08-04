"""Managed one-click installs for registry-owned OmniVoice engines.

Pip engines install into the API environment. Source engines get an isolated
checkout + venv under a configurable data root, with optional resumable
Hugging Face weights. Job state is persisted after every step so a restarted
API can report the last state and a retry can resume healthy artifacts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.tts_pipeline.install_runner import build_tts_install_plan, run_tts_install
from src.tts_pipeline.omnivoice_engine_catalog import OmniVoiceEngineInstall


_GIB = 1024**3
_LOCK = threading.Lock()
_JOBS: dict[str, "EngineInstallJob"] = {}


def _public_text(value: str, root: Path) -> str:
    """Keep managed absolute paths out of API responses and persisted UI logs."""
    text = value or ""
    try:
        resolved = str(root.expanduser().resolve())
    except OSError:
        resolved = str(root)
    return text.replace(resolved, "<managed-engine-root>").replace(
        resolved.replace("\\", "/"), "<managed-engine-root>"
    )


@dataclass
class EngineInstallJob:
    workspace_id: str
    engine_id: str
    root: Path
    status: str = "running"
    step: str = "queued"
    progress: int = 0
    detail: str = "Install queued"
    log: list[str] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def public(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "detail": _public_text(self.detail, self.root),
            "log_tail": _public_text("\n".join(self.log[-80:]), self.root),
            "error": _public_text(self.error, self.root),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _safe_engine_dir(root: Path, engine_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in engine_id).strip("-")
    if not safe:
        raise ValueError("invalid_engine_id")
    resolved_root = root.expanduser().resolve()
    target = (resolved_root / safe).resolve()
    if target.parent != resolved_root:
        raise ValueError("engine_install_path_escaped_root")
    return target


def _state_path(root: Path, engine_id: str) -> Path:
    return _safe_engine_dir(root, engine_id) / "install-state.json"


def _marker_path(root: Path, engine_id: str) -> Path:
    return _safe_engine_dir(root, engine_id) / "installed.json"


def is_managed_engine_installed(engine_id: str, *, root: str | Path) -> bool:
    marker = _marker_path(Path(root), engine_id)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return payload.get("engine_id") == engine_id and payload.get("status") == "installed"


def _persist(job: EngineInstallJob) -> None:
    target = _safe_engine_dir(job.root, job.engine_id)
    target.mkdir(parents=True, exist_ok=True)
    state = target / "install-state.json"
    temp = target / "install-state.json.tmp"
    temp.write_text(json.dumps(job.public(), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(state)


def _update(job: EngineInstallJob, *, step: str, progress: int, detail: str, log: str = "") -> None:
    with _LOCK:
        job.step = step
        job.progress = max(0, min(100, int(progress)))
        job.detail = detail
        entry = log or f"{step}: {detail}"
        if not job.log or job.log[-1] != entry:
            job.log.append(entry)
            del job.log[:-200]
        _persist(job)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 3600,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    execute = runner or subprocess.run
    return execute(
        argv,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def _require_ok(completed: subprocess.CompletedProcess[str], action: str) -> None:
    if completed.returncode == 0:
        return
    tail = "\n".join(((completed.stdout or "") + "\n" + (completed.stderr or "")).splitlines()[-30:])
    raise RuntimeError(f"{action} failed ({completed.returncode}): {tail}")


def _preflight(job: EngineInstallJob, recipe: OmniVoiceEngineInstall) -> None:
    target = _safe_engine_dir(job.root, recipe.engine_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(target.parent).free
    estimate = float(recipe.estimated_size_gb or 1.0)
    required = int((estimate + 2.0) * _GIB)
    if free < required:
        raise RuntimeError(
            f"Insufficient disk space: this engine needs about {estimate:.1f} GB plus 2 GB headroom"
        )
    if recipe.strategy == "source" and shutil.which("git") is None:
        raise RuntimeError("Git is required for this source engine install")


def _install_pip(job: EngineInstallJob, recipe: OmniVoiceEngineInstall) -> None:
    if not recipe.install_command:
        raise RuntimeError("Missing allowlisted pip recipe")
    _update(job, step="install_dependency", progress=35, detail="Installing Python dependency")
    result = run_tts_install(build_tts_install_plan(install_command=recipe.install_command), timeout_seconds=900)
    if not result.ok:
        raise RuntimeError(result.detail + (f"\n{result.log_tail}" if result.log_tail else ""))
    if result.log_tail:
        _update(job, step="install_dependency", progress=65, detail="Dependency installed", log=result.log_tail)


def _install_source(
    job: EngineInstallJob,
    recipe: OmniVoiceEngineInstall,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    if not recipe.repo_url:
        raise RuntimeError("Missing source repository recipe")
    managed = _safe_engine_dir(job.root, recipe.engine_id)
    checkout = managed / "source"
    venv = managed / ".venv"

    if not checkout.exists():
        _update(job, step="clone_repo", progress=15, detail="Cloning engine repository")
        completed = _run(
            ["git", "clone", "--depth", "1", "--recursive", recipe.repo_url, str(checkout)],
            timeout=900,
            runner=runner,
        )
        _require_ok(completed, "Repository clone")
    else:
        _update(job, step="clone_repo", progress=20, detail="Using existing managed checkout")

    python = _venv_python(venv)
    if not python.is_file():
        _update(job, step="create_venv", progress=30, detail="Creating isolated Python environment")
        completed = _run([sys.executable, "-m", "venv", str(venv)], timeout=600, runner=runner)
        _require_ok(completed, "Virtual environment creation")

    _update(job, step="install_dependency", progress=45, detail="Installing engine dependencies")
    args = list(recipe.install_args or ("-e", "."))
    if args[:1] == ["-r"] and len(args) > 1:
        args[1] = str(checkout / args[1])
    elif args == ["-e", "."]:
        args = ["-e", str(checkout)]
    completed = _run([str(python), "-m", "pip", "install", *args], cwd=checkout, runner=runner)
    _require_ok(completed, "Engine dependency install")

    if recipe.weights_repo_id:
        weights = checkout / recipe.weights_subdir
        weights.mkdir(parents=True, exist_ok=True)
        _update(job, step="download_weights", progress=70, detail="Downloading model weights (resumable)")
        hub_probe = _run([str(python), "-c", "import huggingface_hub"], timeout=60, runner=runner)
        if hub_probe.returncode != 0:
            completed = _run(
                [str(python), "-m", "pip", "install", "huggingface-hub"],
                timeout=600,
                runner=runner,
            )
            _require_ok(completed, "Hugging Face downloader install")
        script = (
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download(repo_id={recipe.weights_repo_id!r}, local_dir={str(weights)!r})"
        )
        completed = _run([str(python), "-c", script], timeout=7200, runner=runner)
        _require_ok(completed, "Model weight download")

    if recipe.probe_module:
        _update(job, step="probe", progress=90, detail="Probing installed engine")
        completed = _run([str(python), "-c", f"import {recipe.probe_module}"], timeout=180, runner=runner)
        _require_ok(completed, "Engine import probe")


def execute_engine_install(
    job: EngineInstallJob,
    recipe: OmniVoiceEngineInstall,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    try:
        _update(job, step="preflight", progress=5, detail="Checking platform, tools and disk space")
        _preflight(job, recipe)
        if recipe.strategy == "pip":
            _install_pip(job, recipe)
        elif recipe.strategy == "source":
            _install_source(job, recipe, runner=runner)
        else:
            raise RuntimeError(f"Unsupported automated install strategy: {recipe.strategy}")

        marker = _marker_path(job.root, recipe.engine_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "engine_id": recipe.engine_id,
                    "status": "installed",
                    "strategy": recipe.strategy,
                    "installed_at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        with _LOCK:
            job.status = "succeeded"
            job.step = "complete"
            job.progress = 100
            job.detail = "Engine installation completed; synthesis adapter probe is still authoritative"
            job.finished_at = time.time()
            _persist(job)
    except Exception as exc:  # noqa: BLE001 - captured into an actionable job result
        with _LOCK:
            job.status = "failed"
            job.error = str(exc)
            job.detail = str(exc)
            job.finished_at = time.time()
            job.log.append(str(exc))
            _persist(job)


def start_engine_install(
    *,
    workspace_id: str,
    recipe: OmniVoiceEngineInstall,
    root: str | Path,
    force_reinstall: bool = False,
) -> dict[str, Any]:
    key = str(workspace_id)
    root_path = Path(root)
    with _LOCK:
        for existing in _JOBS.values():
            if existing.status == "running":
                if existing.engine_id == recipe.engine_id:
                    return {**existing.public(), "status": "already_running"}
                raise RuntimeError(f"Another engine install is already running: {existing.engine_id}")
        if not force_reinstall and is_managed_engine_installed(recipe.engine_id, root=root_path):
            return {
                "status": "already_installed",
                "engine_id": recipe.engine_id,
                "step": "complete",
                "progress": 100,
                "detail": "Managed engine installation is already complete",
                "log_tail": "",
                "error": "",
                "started_at": None,
                "finished_at": None,
            }
        job = EngineInstallJob(workspace_id=key, engine_id=recipe.engine_id, root=root_path)
        _JOBS[key] = job
        _persist(job)

    thread = threading.Thread(
        target=execute_engine_install,
        args=(job, recipe),
        name=f"tts-engine-install-{recipe.engine_id}",
        daemon=True,
    )
    thread.start()
    return job.public()


def get_engine_install_status(*, workspace_id: str, root: str | Path) -> dict[str, Any] | None:
    key = str(workspace_id)
    with _LOCK:
        job = _JOBS.get(key)
        if job is not None:
            return job.public()
    root_path = Path(root)
    if not root_path.exists():
        return None
    states = sorted(root_path.glob("*/install-state.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for state in states:
        try:
            payload = json.loads(state.read_text(encoding="utf-8"))
            if payload.get("status") == "running":
                payload["status"] = "interrupted"
                payload["detail"] = "A previous install was interrupted; press Install engine to resume"
            return payload
        except (OSError, ValueError):
            continue
    return None


def reset_engine_install_jobs_for_tests() -> None:
    with _LOCK:
        _JOBS.clear()
