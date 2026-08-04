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
        source = inspect.getsource(app._init_classic_paddleocr)
        self.assertIn("enable_mkldnn", source)
        # Default / Cloud Run path keeps False fallback; angle cls off for Douyin.
        self.assertIn("False", source)
        self.assertIn('"use_angle_cls": False', source.replace("'", '"'))
        self.assertIn("configure_paddle_cpu_safe_runtime", source)
        self.assertIn("configure_paddle_cpu_safe_runtime", inspect.getsource(app.get_ocr_engine))

    def test_classic_init_prefers_no_angle_cls(self) -> None:
        app = _load_cloud_run_app()
        source = inspect.getsource(app._init_classic_paddleocr)
        self.assertIn("use_angle_cls", source)
        self.assertIn("False", source)
        self.assertIn("PP-OCRv4", source)

    def test_classic_init_pins_observed_ppocrv6_medium_models(self) -> None:
        app = _load_cloud_run_app()
        source = inspect.getsource(app._init_classic_paddleocr)

        self.assertEqual(app.CLASSIC_DETECTION_MODEL, "PP-OCRv6_medium_det")
        self.assertEqual(app.CLASSIC_RECOGNITION_MODEL, "PP-OCRv6_medium_rec")
        self.assertIn("CLASSIC_DETECTION_MODEL", source)
        self.assertIn("CLASSIC_RECOGNITION_MODEL", source)

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

    def test_resolve_engine_mode_auto_and_explicit(self) -> None:
        app = _load_cloud_run_app()
        os.environ.pop("OCR_PADDLE_VL_INPROCESS", None)
        os.environ["OCR_PADDLE_ENGINE"] = "classic"
        self.assertEqual(app.resolve_engine_mode(), "classic")
        os.environ["OCR_PADDLE_ENGINE"] = "vl16"
        self.assertEqual(app.resolve_engine_mode(), "vl16")
        os.environ["OCR_PADDLE_ENGINE"] = "auto"
        # Without /proc/meminfo (Windows host tests), auto prefers vl16;
        # container low-RAM path is covered by health fields after deploy.
        mode = app.resolve_engine_mode()
        self.assertIn(mode, {"classic", "vl16"})
        self.assertEqual(app.engine_request_label(), "auto")

    def test_health_reports_pinned_classic_model_version(self) -> None:
        app = _load_cloud_run_app()
        os.environ["OCR_PADDLE_ENGINE"] = "classic"
        app._engine_kind = None

        payload = app.health()

        self.assertEqual(payload["ocr_model_version"], "ppocrv6-medium-det-rec")

    def test_parse_vl_parsing_res_list(self) -> None:
        """PaddleOCR-VL JSON uses parsing_res_list + coordinate boxes."""
        app = _load_cloud_run_app()
        payload = {
            "res": {
                "parsing_res_list": [
                    {
                        "block_label": "text",
                        "block_content": "让你解馋",
                        "block_bbox": [10, 100, 200, 140],
                        "block_score": 0.97,
                    },
                    {
                        "block_label": "image",
                        "block_content": "",
                        "coordinate": [0, 0, 50, 50],
                    },
                ]
            }
        }
        items = app.parse_paddle_ocr_result([payload])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "让你解馋")
        self.assertEqual(len(items[0]["bbox"]), 4)
        self.assertGreaterEqual(items[0]["score"], 0.9)

    def test_get_ocr_engine_falls_back_to_classic_when_vl_fails(self) -> None:
        app = _load_cloud_run_app()
        app._ocr_engine = None
        app._engine_kind = None
        os.environ["OCR_PADDLE_ENGINE"] = "vl16"
        os.environ.pop("OCR_PADDLE_NO_FALLBACK", None)

        class _Classic:
            def ocr(self, *_a, **_k):
                return []

        def _boom_vl(**_kwargs):
            raise RuntimeError("OOM simulated")

        def _classic(**_kwargs):
            return _Classic()

        import types
        import sys

        fake_paddleocr = types.SimpleNamespace(
            PaddleOCRVL=_boom_vl,
            PaddleOCR=_classic,
        )

        sys.modules["paddleocr"] = fake_paddleocr  # type: ignore[assignment]
        try:
            # Force re-import path: get_ocr_engine imports paddleocr inside.
            engine = app.get_ocr_engine()
            self.assertIsInstance(engine, _Classic)
            self.assertEqual(app._engine_kind, "classic")
            self.assertTrue(app._engine_fallback)
        finally:
            sys.modules.pop("paddleocr", None)
            app._ocr_engine = None
            app._engine_kind = None
            app._engine_fallback = False

    def test_get_ocr_engine_no_fallback_when_strict_vl16(self) -> None:
        """Explicit VL QA: OCR_PADDLE_NO_FALLBACK=1 must not switch to classic."""
        app = _load_cloud_run_app()
        app._ocr_engine = None
        app._engine_kind = None
        os.environ["OCR_PADDLE_ENGINE"] = "vl16"
        os.environ["OCR_PADDLE_NO_FALLBACK"] = "1"

        def _boom_vl(**_kwargs):
            raise RuntimeError("OOM simulated")

        import types
        import sys

        sys.modules["paddleocr"] = types.SimpleNamespace(  # type: ignore[assignment]
            PaddleOCRVL=_boom_vl,
            PaddleOCR=lambda **_k: object(),
        )
        try:
            with self.assertRaises(RuntimeError) as ctx:
                app.get_ocr_engine()
            self.assertIn("no-fallback", str(ctx.exception).lower())
            self.assertNotEqual(app._engine_kind, "classic")
            self.assertFalse(app._engine_fallback)
        finally:
            sys.modules.pop("paddleocr", None)
            os.environ.pop("OCR_PADDLE_NO_FALLBACK", None)
            app._ocr_engine = None
            app._engine_kind = None
            app._engine_fallback = False


if __name__ == "__main__":
    unittest.main()
