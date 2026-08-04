from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.adaptive_typography import (
    TypographyLayoutError,
    plan_dense_grid_layouts,
    plan_text_layout,
)


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class ResponsiveTypographyTests(unittest.TestCase):
    def test_hardsub_wraps_to_two_lines_inside_safe_area(self) -> None:
        background = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        layout = plan_text_layout(
            "Mỗi ngày mình đều lên món ăn kiêng siêu ngon với 200 g cơm",
            kind="hardsub",
            safe_area={"x": 0.1, "y": 0.65, "width": 0.8, "height": 0.25},
            frame_width=1920,
            frame_height=1080,
            fontfile=_font(),
            background_bgr=background,
            max_lines=2,
        )
        self.assertLessEqual(len(layout.lines), 2)
        self.assertGreaterEqual(layout.x0, int(0.1 * 1920))
        self.assertLessEqual(layout.x0 + layout.width, int(0.9 * 1920) + 1)
        self.assertFalse(any(line.endswith("200") for line in layout.lines))

    def test_ui_shrinks_within_limits_and_keeps_safe_margin(self) -> None:
        background = np.full((400, 600, 3), 230, dtype=np.uint8)
        layout = plan_text_layout(
            "Nước tương 2 muỗng",
            kind="ui",
            safe_area={"x": 0.025, "y": 0.2, "width": 0.25, "height": 0.15},
            frame_width=600,
            frame_height=400,
            fontfile=_font(),
            background_bgr=background,
            max_lines=1,
        )
        self.assertGreaterEqual(layout.x0, 15)
        self.assertLessEqual(layout.x0 + layout.width, 165)
        self.assertEqual(layout.fill_rgb, (28, 28, 28))

    def test_dark_background_selects_white_text_once_per_track(self) -> None:
        background = np.full((200, 300, 3), 20, dtype=np.uint8)
        layout = plan_text_layout(
            "Bữa trưa",
            kind="ui",
            safe_area={"x": 0.05, "y": 0.05, "width": 0.4, "height": 0.2},
            frame_width=300,
            frame_height=200,
            fontfile=_font(),
            background_bgr=background,
            max_lines=1,
        )
        self.assertEqual(layout.fill_rgb, (255, 255, 255))
        self.assertEqual(layout.stroke_rgb, (0, 0, 0))

    def test_dense_grid_stays_inside_frame_without_collision(self) -> None:
        background = np.full((720, 1280, 3), 70, dtype=np.uint8)
        items = [
            {"text_id": f"t{i}", "text": f"Nhãn {i}", "side": "left" if i < 5 else "right"}
            for i in range(10)
        ]
        layouts = plan_dense_grid_layouts(
            items,
            safe_area={"x": 0.04, "y": 0.05, "width": 0.92, "height": 0.9},
            frame_width=1280,
            frame_height=720,
            fontfile=_font(),
            background_bgr=background,
        )
        self.assertEqual(len(layouts), 10)
        rects = []
        for item in layouts:
            layout = item["layout"]
            rect = (layout.x0, layout.y0, layout.x0 + layout.width, layout.y0 + layout.height)
            self.assertGreaterEqual(rect[0], 0)
            self.assertGreaterEqual(rect[1], 0)
            self.assertLessEqual(rect[2], 1280)
            self.assertLessEqual(rect[3], 720)
            rects.append(rect)
        for index, rect in enumerate(rects):
            for other in rects[index + 1 :]:
                overlap = not (
                    rect[2] <= other[0]
                    or other[2] <= rect[0]
                    or rect[3] <= other[1]
                    or other[3] <= rect[1]
                )
                self.assertFalse(overlap)

    def test_blocks_unreadable_text_instead_of_truncating(self) -> None:
        background = np.zeros((100, 100, 3), dtype=np.uint8)
        with self.assertRaises(TypographyLayoutError):
            plan_text_layout(
                "Một câu quá dài không thể nằm trong ô cực nhỏ này",
                kind="ui",
                safe_area={"x": 0.1, "y": 0.1, "width": 0.08, "height": 0.05},
                frame_width=100,
                frame_height=100,
                fontfile=_font(),
                background_bgr=background,
                max_lines=1,
            )

    def test_dense_grid_balances_columns_when_source_side_is_over_capacity(self) -> None:
        background = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        items = [
            {
                "text_id": f"t{i}",
                "text": (
                    "Có riêng kho dữ liệu thực phẩm"
                    if i == 1
                    else f"Nhãn {i}"
                ),
                "side": "left",
            }
            for i in range(29)
        ]

        layouts = plan_dense_grid_layouts(
            items,
            safe_area={"x": 0.04, "y": 0.05, "width": 0.92, "height": 0.9},
            frame_width=1920,
            frame_height=1080,
            fontfile=_font(),
            background_bgr=background,
        )

        self.assertEqual(len(layouts), 29)
        self.assertEqual(
            {item["placement_mode"] for item in layouts},
            {"balanced_capacity_fallback"},
        )

    def test_dense_grid_stable_slot_does_not_reflow_when_peer_disappears(self) -> None:
        background = np.full((720, 1280, 3), 70, dtype=np.uint8)
        safe_area = {"x": 0.04, "y": 0.05, "width": 0.92, "height": 0.9}
        first = {
            "text_id": "first",
            "text": "Nhãn đầu",
            "side": "left",
            "stable_slot": {"side": "left", "slot_index": 0, "slot_count": 2},
        }
        second = {
            "text_id": "second",
            "text": "Nhãn sau",
            "side": "left",
            "stable_slot": {"side": "left", "slot_index": 1, "slot_count": 2},
        }

        together = plan_dense_grid_layouts(
            [first, second],
            safe_area=safe_area,
            frame_width=1280,
            frame_height=720,
            fontfile=_font(),
            background_bgr=background,
        )
        second_only = plan_dense_grid_layouts(
            [second],
            safe_area=safe_area,
            frame_width=1280,
            frame_height=720,
            fontfile=_font(),
            background_bgr=background,
        )

        together_second = next(
            item["layout"] for item in together if item["text_id"] == "second"
        )
        self.assertEqual(second_only[0]["layout"].x0, together_second.x0)
        self.assertEqual(second_only[0]["layout"].y0, together_second.y0)

    def test_dense_grid_preserves_source_relative_vertical_group_spacing(self) -> None:
        background = np.full((720, 1280, 3), 70, dtype=np.uint8)
        items = [
            {
                "text_id": text_id,
                "text": text,
                "side": "left",
                "geometry": {"x": 0.14, "y": y, "width": 0.12, "height": 0.05},
                "stable_slot": {"side": "left", "slot_index": index, "slot_count": 4},
            }
            for index, (text_id, text, y) in enumerate(
                (
                    ("top", "Hành lá", 0.14),
                    ("upper", "Tỏi băm", 0.22),
                    ("lower", "Dầu mè 4 g", 0.52),
                    ("bottom", "Nước dùng mì vừa đủ", 0.74),
                )
            )
        ]

        layouts = plan_dense_grid_layouts(
            items,
            safe_area={"x": 0.04, "y": 0.05, "width": 0.92, "height": 0.9},
            frame_width=1280,
            frame_height=720,
            fontfile=_font(),
            background_bgr=background,
        )

        self.assertEqual({item["placement_mode"] for item in layouts}, {"source_relative"})
        by_id = {item["text_id"]: item["layout"] for item in layouts}
        # The source group spans roughly 0.65 frame height, not the full 0.90
        # safe area used by the generic dashboard grid.
        rendered_span = by_id["bottom"].y0 + by_id["bottom"].height - by_id["top"].y0
        self.assertLess(rendered_span, int(round(720 * 0.78)))
        self.assertLess(by_id["top"].y0, by_id["upper"].y0)
        self.assertLess(by_id["upper"].y0, by_id["lower"].y0)
        self.assertLess(by_id["lower"].y0, by_id["bottom"].y0)

    def test_micro_ui_uses_smaller_but_still_legible_type_scale(self) -> None:
        background = np.full((720, 1280, 3), 90, dtype=np.uint8)
        layout = plan_text_layout(
            "510 kcal",
            kind="micro_ui",
            safe_area={"x": 0.35, "y": 0.45, "width": 0.30, "height": 0.055},
            frame_width=1280,
            frame_height=720,
            fontfile=_font(),
            background_bgr=background,
            max_lines=1,
        )

        self.assertGreaterEqual(layout.font_size_px, 12)
        self.assertLessEqual(layout.font_size_px, round(720 * 0.022))


if __name__ == "__main__":
    unittest.main()
