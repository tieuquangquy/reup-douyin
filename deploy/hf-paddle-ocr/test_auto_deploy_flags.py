"""Contracts for Cloud Run deploy flags parsed from README / CLI."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import auto_deploy  # noqa: E402


class AutoDeployFlagsTests(unittest.TestCase):
    def test_readme_defaults_include_vl16_profile(self) -> None:
        cfg = auto_deploy.parse_deploy_defaults_from_readme(SCRIPT_DIR / "README_DEPLOY.md")
        self.assertEqual(cfg["service"], "paddle-ocr-vl16")
        self.assertEqual(cfg["concurrency"], "1")
        self.assertEqual(cfg["region"], "us-central1")
        self.assertEqual(cfg["min_instances"], "0")
        self.assertEqual(cfg["cpu"], "4")
        self.assertEqual(cfg["memory"], "16Gi")
        self.assertEqual(cfg["timeout"], "3600")
        self.assertEqual(cfg["max_instances"], "1")
        self.assertIn("OCR_PADDLE_ENGINE=vl16", cfg["set_env_vars"])
        self.assertIn("OCR_PADDLE_NO_FALLBACK=1", cfg["set_env_vars"])

    def test_build_deploy_command_passes_vl16_env_and_concurrency(self) -> None:
        cfg = {
            "service": "paddle-ocr-vl16",
            "region": "us-central1",
            "memory": "16Gi",
            "cpu": "4",
            "concurrency": "1",
            "min_instances": "0",
            "max_instances": "1",
            "port": "8080",
            "timeout": "3600",
            "set_env_vars": auto_deploy.DEFAULT_SET_ENV_VARS,
        }
        cmd = auto_deploy.build_deploy_command(cfg, source_dir=SCRIPT_DIR)
        self.assertIn("--concurrency", cmd)
        self.assertEqual(cmd[cmd.index("--concurrency") + 1], "1")
        self.assertEqual(cmd[cmd.index("--memory") + 1], "16Gi")
        self.assertEqual(cmd[cmd.index("--timeout") + 1], "3600")
        self.assertEqual(cmd[cmd.index("--region") + 1], "us-central1")
        self.assertIn("--set-env-vars", cmd)
        env_vals = cmd[cmd.index("--set-env-vars") + 1]
        self.assertIn("OCR_PADDLE_ENGINE=vl16", env_vals)
        self.assertIn("OCR_PADDLE_NO_FALLBACK=1", env_vals)

    def test_warm_flag_sets_min_instances_one_in_dry_run_command(self) -> None:
        from io import StringIO
        from unittest.mock import patch

        buf = StringIO()
        with patch("sys.stdout", buf):
            code = auto_deploy.main(
                [
                    "--dry-run",
                    "--warm",
                    "--service",
                    "paddle-ocr-vl16",
                ]
            )
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("--concurrency 1", out)
        self.assertIn("--min-instances 1", out)
        self.assertIn("--memory 16Gi", out)
        self.assertIn("--region us-central1", out)
        self.assertIn("OCR_PADDLE_ENGINE=vl16", out)


if __name__ == "__main__":
    unittest.main()
