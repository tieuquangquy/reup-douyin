"""Unit tests for LocalTextDetector preprocess/postprocess (mocked ONNX)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import (
    LocalTextDetector,
    resolve_dbnet_execution_providers,
    TextBox,
    box_iou,
    expand_text_boxes,
    has_new_text_boxes,
    merge_collinear_text_boxes,
    postprocess_prob_map,
    preprocess_bgr_for_dbnet,
)


class PreprocessPostprocessTests(unittest.TestCase):
    def test_preprocess_returns_nchw_float32(self) -> None:
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        tensor, scale, (pad_h, pad_w) = preprocess_bgr_for_dbnet(frame)
        self.assertEqual(tensor.ndim, 4)
        self.assertEqual(tensor.shape[0], 1)
        self.assertEqual(tensor.shape[1], 3)
        self.assertEqual(tensor.dtype, np.float32)
        self.assertGreater(scale, 0.0)
        self.assertEqual(pad_h % 32, 0)
        self.assertEqual(pad_w % 32, 0)

    def test_preprocess_long_edge_is_640(self) -> None:
        """Higher long-edge improves recall on 1080p Douyin frames."""
        from src.media_pipeline.frame_sampling.local_text_detector import _DET_LONG_EDGE

        self.assertEqual(_DET_LONG_EDGE, 640)
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        tensor, scale, _ = preprocess_bgr_for_dbnet(frame)
        # Long side of network canvas before pad is 640; after pad ≤ 640+31.
        self.assertLessEqual(max(int(tensor.shape[2]), int(tensor.shape[3])), 640 + 31)
        self.assertAlmostEqual(scale, 640 / 640, places=5)

    def test_postprocess_finds_blob_as_box(self) -> None:
        prob = np.zeros((160, 160), dtype=np.float32)
        prob[40:80, 20:100] = 0.9
        boxes = postprocess_prob_map(prob, orig_h=480, orig_w=640, scale=160 / 640)
        self.assertGreaterEqual(len(boxes), 1)
        b = boxes[0]
        self.assertGreater(b.width, 0.05)
        self.assertGreater(b.height, 0.02)


class ExpandMergeTextBoxTests(unittest.TestCase):
    def test_expand_grows_box_and_clamps(self) -> None:
        box = TextBox(x=0.10, y=0.80, width=0.20, height=0.04)
        expanded = expand_text_boxes([box], pad_w_frac=0.08, pad_h_frac=0.20)
        self.assertEqual(len(expanded), 1)
        e = expanded[0]
        self.assertLess(e.x, box.x)
        self.assertLess(e.y, box.y)
        self.assertGreater(e.width, box.width)
        self.assertGreater(e.height, box.height)
        self.assertGreaterEqual(e.x, 0.0)
        self.assertGreaterEqual(e.y, 0.0)
        self.assertLessEqual(e.x + e.width, 1.0 + 1e-6)
        self.assertLessEqual(e.y + e.height, 1.0 + 1e-6)

    def test_merge_collinear_fragments_into_one_line(self) -> None:
        # Truncated caption + trailing fragment on same baseline (f720-like).
        left = TextBox(x=0.04, y=0.86, width=0.27, height=0.033)
        right = TextBox(x=0.32, y=0.87, width=0.08, height=0.030)
        merged = merge_collinear_text_boxes([left, right])
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertLessEqual(m.x, left.x + 1e-6)
        self.assertGreaterEqual(m.x + m.width, right.x + right.width - 1e-6)

    def test_merge_does_not_join_different_rows(self) -> None:
        top = TextBox(x=0.70, y=0.25, width=0.08, height=0.03)
        bottom = TextBox(x=0.04, y=0.86, width=0.30, height=0.03)
        merged = merge_collinear_text_boxes([top, bottom])
        self.assertEqual(len(merged), 2)


class IoUGateTests(unittest.TestCase):
    def test_new_box_when_no_overlap(self) -> None:
        prev = [TextBox(0.1, 0.8, 0.5, 0.08)]
        cur = [TextBox(0.1, 0.2, 0.4, 0.06)]
        self.assertTrue(has_new_text_boxes(cur, prev, iou_new_thresh=0.3))

    def test_skip_when_same_box(self) -> None:
        prev = [TextBox(0.1, 0.8, 0.5, 0.08)]
        cur = [TextBox(0.11, 0.81, 0.48, 0.07)]
        self.assertGreater(box_iou(prev[0], cur[0]), 0.5)
        self.assertFalse(has_new_text_boxes(cur, prev, iou_new_thresh=0.3))

    def test_default_iou_thresh_is_point_three(self) -> None:
        """Default gate: max IoU < 0.3 counts as new text."""
        from src.media_pipeline.frame_sampling.text_change_sampler import DEFAULT_IOU_NEW_THRESH

        self.assertEqual(DEFAULT_IOU_NEW_THRESH, 0.3)
        prev = [TextBox(0.1, 0.8, 0.5, 0.1)]
        self.assertFalse(has_new_text_boxes(prev, prev))
        far = [TextBox(0.1, 0.2, 0.5, 0.1)]
        self.assertTrue(has_new_text_boxes(far, prev))


class LocalTextDetectorLoadTests(unittest.TestCase):
    def test_execution_provider_defaults_to_cpu_for_locked_baseline(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                resolve_dbnet_execution_providers(
                    ["DmlExecutionProvider", "CPUExecutionProvider"]
                ),
                ["CPUExecutionProvider"],
            )

    def test_execution_provider_uses_explicit_directml_with_cpu_fallback(self) -> None:
        with patch.dict("os.environ", {"DBNET_ONNX_PROVIDER": "directml"}):
            self.assertEqual(
                resolve_dbnet_execution_providers(
                    ["DmlExecutionProvider", "CPUExecutionProvider"]
                ),
                ["DmlExecutionProvider", "CPUExecutionProvider"],
            )

    def test_detect_uses_session_run(self) -> None:
        frame = np.full((240, 320, 3), 90, dtype=np.uint8)
        fake_out = np.zeros((1, 1, 160, 160), dtype=np.float32)
        fake_out[0, 0, 50:90, 30:110] = 0.95
        session = MagicMock()
        session.run.return_value = [fake_out]

        det = object.__new__(LocalTextDetector)
        det._session = session
        det._input_name = "x"
        det.model_path = Path("fake.onnx")
        boxes = det.detect(frame)
        self.assertGreaterEqual(len(boxes), 1)
        session.run.assert_called_once()

    def test_detect_accepts_high_resolution_long_edge(self) -> None:
        frame = np.full((180, 960, 3), 90, dtype=np.uint8)
        session = MagicMock()
        session.run.return_value = [np.zeros((1, 1, 192, 960), dtype=np.float32)]
        det = object.__new__(LocalTextDetector)
        det._session = session
        det._input_name = "x"
        det.model_path = Path("fake.onnx")

        det.detect(frame, long_edge=960)

        tensor = session.run.call_args.args[1]["x"]
        self.assertEqual(tensor.shape[3], 960)


if __name__ == "__main__":
    unittest.main()
