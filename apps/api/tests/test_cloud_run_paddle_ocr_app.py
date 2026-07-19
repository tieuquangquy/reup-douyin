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


class _FakePaddleResultPropertyJson:
    """PaddleOCR 3.x Result: ``.json`` is a property (dict), not a callable."""

    @property
    def json(self):
        return {
            "res": {
                "dt_polys": [[[10, 100], [200, 100], [200, 140], [10, 140]]],
                "rec_texts": ["你好世界"],
                "rec_scores": [0.99],
            }
        }


class _FakePaddleResultMapping:
    def keys(self):
        return ("dt_polys", "rec_texts", "rec_scores")

    def __getitem__(self, key):
        data = {
            "dt_polys": [[[10, 100], [200, 100], [200, 140], [10, 140]]],
            "rec_texts": ["硬字幕"],
            "rec_scores": [0.95],
        }
        return data[key]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


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

    def test_parse_property_json_nested_res(self) -> None:
        """Regression: HTTP 200 + [] when Result.json is a property with nested res."""
        app = _load_cloud_run_app()
        items = app.parse_paddle_ocr_result([_FakePaddleResultPropertyJson()])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "你好世界")
        self.assertGreaterEqual(items[0]["score"], 0.9)
        self.assertEqual(len(items[0]["bbox"]), 4)

    def test_parse_mapping_like_result(self) -> None:
        app = _load_cloud_run_app()
        items = app.parse_paddle_ocr_result([_FakePaddleResultMapping()])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "硬字幕")

    def test_parse_top_level_res_dict(self) -> None:
        app = _load_cloud_run_app()
        items = app.parse_paddle_ocr_result(
            [{"res": {"dt_polys": [[[1, 2], [3, 2], [3, 4], [1, 4]]], "rec_texts": ["测"], "rec_scores": [0.8]}}]
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "测")


if __name__ == "__main__":
    unittest.main()
