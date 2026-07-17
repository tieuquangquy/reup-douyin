"""Cloud Run PaddleOCR app must disable oneDNN/MKLDNN (same crash as local Paddle 3.3.x)."""

from __future__ import annotations

import importlib.util
import inspect
import os
import unittest
from pathlib import Path


def _load_cloud_run_app():
    path = (
        Path(__file__).resolve().parents[3]
        / "deploy"
        / "hf-paddle-ocr"
        / "app.py"
    )
    spec = importlib.util.spec_from_file_location("hf_paddle_ocr_app", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudRunPaddleOcrAppRuntimeTests(unittest.TestCase):
    def test_configure_forces_mkldnn_off(self) -> None:
        app = _load_cloud_run_app()
        self.assertTrue(hasattr(app, "configure_paddle_cpu_safe_runtime"))
        os.environ["FLAGS_use_mkldnn"] = "1"
        os.environ["FLAGS_onednn"] = "1"
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "1"
        app.configure_paddle_cpu_safe_runtime()
        self.assertEqual(os.environ["FLAGS_use_mkldnn"], "0")
        self.assertEqual(os.environ["FLAGS_onednn"], "0")
        self.assertEqual(os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"], "0")

    def test_get_ocr_engine_passes_enable_mkldnn_false(self) -> None:
        app = _load_cloud_run_app()
        source = inspect.getsource(app.get_ocr_engine)
        self.assertIn("enable_mkldnn", source)
        self.assertIn("False", source)
        self.assertIn("configure_paddle_cpu_safe_runtime", source)

    def test_startup_does_not_preload_paddle(self) -> None:
        """Scale-to-zero: preload blocks readiness and causes client 503s."""
        app = _load_cloud_run_app()
        self.assertFalse(hasattr(app, "preload_ocr_on_startup"))
        if hasattr(app, "lifespan"):
            source = inspect.getsource(app.lifespan)
            self.assertNotIn("get_ocr_engine", source)


if __name__ == "__main__":
    unittest.main()
