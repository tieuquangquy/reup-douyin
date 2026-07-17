"""Paddle CPU-safe env must disable MKLDNN/PIR before inference."""

from __future__ import annotations

import os
import unittest

from src.ocr_pipeline.providers import _configure_paddle_cpu_safe_runtime


class PaddleCpuSafeRuntimeTests(unittest.TestCase):
    def test_configure_forces_mkldnn_off_even_if_previously_on(self) -> None:
        os.environ["FLAGS_use_mkldnn"] = "1"
        os.environ["FLAGS_onednn"] = "1"
        os.environ["FLAGS_enable_pir_api"] = "1"
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "1"

        _configure_paddle_cpu_safe_runtime()

        self.assertEqual(os.environ["FLAGS_use_mkldnn"], "0")
        self.assertEqual(os.environ["FLAGS_onednn"], "0")
        self.assertEqual(os.environ["FLAGS_enable_pir_api"], "0")
        self.assertEqual(os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"], "0")


if __name__ == "__main__":
    unittest.main()
