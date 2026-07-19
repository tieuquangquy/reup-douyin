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
    def test_readme_defaults_include_concurrency_two(self) -> None:
        cfg = auto_deploy.parse_deploy_defaults_from_readme(SCRIPT_DIR / "README_DEPLOY.md")
        self.assertEqual(cfg["concurrency"], "2")
        self.assertEqual(cfg["region"], "asia-southeast1")
        self.assertEqual(cfg["min_instances"], "0")
        self.assertEqual(cfg["cpu"], "4")
        self.assertEqual(cfg["memory"], "8Gi")

    def test_build_deploy_command_passes_concurrency(self) -> None:
        cfg = {
            "service": "paddle-ocr-api",
            "region": "asia-southeast1",
            "memory": "8Gi",
            "cpu": "4",
            "concurrency": "2",
            "min_instances": "0",
            "max_instances": "3",
            "port": "8080",
            "timeout": "300",
        }
        cmd = auto_deploy.build_deploy_command(cfg, source_dir=SCRIPT_DIR)
        self.assertIn("--concurrency", cmd)
        self.assertEqual(cmd[cmd.index("--concurrency") + 1], "2")
        self.assertEqual(cmd[cmd.index("--region") + 1], "asia-southeast1")

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
                    "paddle-ocr-api",
                ]
            )
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("--concurrency 2", out)
        self.assertIn("--min-instances 1", out)
        self.assertIn("--region asia-southeast1", out)


if __name__ == "__main__":
    unittest.main()
