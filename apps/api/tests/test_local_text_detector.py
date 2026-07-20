"""Unit tests for LocalTextDetector preprocess/postprocess (mocked ONNX)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import (
    LocalTextDetector,
    TextBox,
    box_iou,
    has_new_text_boxes,
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

    def test_preprocess_long_edge_is_320(self) -> None:
        """chineseocr_lite dbnet.onnx expects ~320 long-edge (not 640)."""
        from src.media_pipeline.frame_sampling.local_text_detector import _DET_LONG_EDGE

        self.assertEqual(_DET_LONG_EDGE, 320)
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        tensor, scale, _ = preprocess_bgr_for_dbnet(frame)
        # Long side of network canvas before pad is 320; after pad still ≤ 320+31.
        self.assertLessEqual(max(int(tensor.shape[2]), int(tensor.shape[3])), 320)
        self.assertAlmostEqual(scale, 320 / 640, places=5)

    def test_postprocess_finds_blob_as_box(self) -> None:
        prob = np.zeros((160, 160), dtype=np.float32)
        prob[40:80, 20:100] = 0.9
        boxes = postprocess_prob_map(prob, orig_h=480, orig_w=640, scale=160 / 640)
        self.assertGreaterEqual(len(boxes), 1)
        b = boxes[0]
        self.assertGreater(b.width, 0.05)
        self.assertGreater(b.height, 0.02)


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


if __name__ == "__main__":
    unittest.main()
