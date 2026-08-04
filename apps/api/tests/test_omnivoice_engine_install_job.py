import json
import subprocess
from pathlib import Path

from src.tts_pipeline.omnivoice_engine_catalog import OmniVoiceEngineInstall
from src.tts_pipeline.omnivoice_engine_install_job import (
    EngineInstallJob,
    execute_engine_install,
    get_engine_install_status,
    is_managed_engine_installed,
)


def _successful_runner(commands: list[list[str]]):
    def run(argv, **_kwargs):
        commands.append([str(value) for value in argv])
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    return run


def test_source_install_uses_registry_recipe_and_persists_success(tmp_path, monkeypatch):
    commands: list[list[str]] = []
    monkeypatch.setattr("src.tts_pipeline.omnivoice_engine_install_job.shutil.which", lambda name: name)
    recipe = OmniVoiceEngineInstall(
        engine_id="test-source",
        strategy="source",
        repo_url="https://example.invalid/allowlisted-engine.git",
        install_args=("-e", "."),
        probe_module="allowlisted_engine",
        estimated_size_gb=0.01,
    )
    job = EngineInstallJob(workspace_id="workspace", engine_id=recipe.engine_id, root=tmp_path)

    execute_engine_install(job, recipe, runner=_successful_runner(commands))

    assert job.status == "succeeded"
    assert job.progress == 100
    assert is_managed_engine_installed(recipe.engine_id, root=tmp_path) is True
    assert commands[0][:5] == ["git", "clone", "--depth", "1", "--recursive"]
    assert any(command[-2:] == ["-e", str(tmp_path / "test-source" / "source")] for command in commands)
    assert any("import allowlisted_engine" in command[-1] for command in commands)

    state = json.loads((tmp_path / "test-source" / "install-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["step"] == "complete"
    assert "clone_repo" in state["log_tail"]


def test_persisted_running_job_is_reported_as_interrupted_after_restart(tmp_path):
    state_dir = tmp_path / "test-source"
    state_dir.mkdir()
    (state_dir / "install-state.json").write_text(
        json.dumps(
            {
                "engine_id": "test-source",
                "status": "running",
                "step": "download_weights",
                "progress": 70,
                "detail": "Downloading",
                "log_tail": "",
                "error": "",
                "started_at": 1.0,
                "finished_at": None,
            }
        ),
        encoding="utf-8",
    )

    status = get_engine_install_status(workspace_id="workspace", root=tmp_path)

    assert status is not None
    assert status["status"] == "interrupted"
    assert "resume" in status["detail"].lower()


def test_public_job_payload_redacts_managed_absolute_path(tmp_path):
    job = EngineInstallJob(workspace_id="workspace", engine_id="test-source", root=tmp_path)
    job.detail = f"Failed under {tmp_path.resolve()}"
    job.error = job.detail
    job.log.append(job.detail)

    payload = job.public()

    assert str(tmp_path.resolve()) not in payload["detail"]
    assert "<managed-engine-root>" in payload["detail"]
