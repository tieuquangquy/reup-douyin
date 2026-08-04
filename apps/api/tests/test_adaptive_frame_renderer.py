from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
    _default_mask_builder,
)
from src.media_pipeline.video_renderer.render_policy import plan_render_track


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


def _track(**overrides: object) -> dict:
    row = {
        "text_id": "sub_a",
        "content_id": "content_a",
        "start_ms": 0,
        "end_ms": 1000,
        "geometry": {"x": 0.35, "y": 0.78, "width": 0.3, "height": 0.06},
        "kind": "hardsub",
        "roles": ["hardsub"],
        "text_vi": "Phụ đề tiếng Việt",
        "cover_only": False,
    }
    row.update(overrides)
    row["render_policy"] = plan_render_track(
        row,
        simultaneous_count=int(row.pop("simultaneous_count", 1)),
    )
    return row


def _mask_builder(frame: np.ndarray, track: dict) -> np.ndarray:
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    geometry = track["geometry"]
    height, width = frame.shape[:2]
    x0 = int(geometry["x"] * width)
    y0 = int(geometry["y"] * height)
    x1 = int((geometry["x"] + geometry["width"]) * width)
    y1 = int((geometry["y"] + geometry["height"]) * height)
    # Ink-like stripes, not a filled AABB.
    mask[y0:y1:2, x0:x1] = 255
    return mask


class AdaptiveFrameRendererTests(unittest.TestCase):
    def test_dense_layout_authority_reuses_only_non_overlapping_slots(self) -> None:
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        tracks = [
            _track(
                text_id="dense_a",
                start_frame=0,
                end_frame=10,
                geometry={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.04},
                kind="ui",
                roles=["ui_chip"],
                simultaneous_count=3,
            ),
            _track(
                text_id="dense_b",
                start_frame=5,
                end_frame=15,
                geometry={"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.04},
                kind="ui",
                roles=["ui_chip"],
                simultaneous_count=3,
            ),
            _track(
                text_id="dense_c",
                start_frame=16,
                end_frame=20,
                geometry={"x": 0.1, "y": 0.3, "width": 0.1, "height": 0.04},
                kind="ui",
                roles=["ui_chip"],
                simultaneous_count=3,
            ),
        ]
        for track in tracks:
            track["render_policy"]["context"]["dense_ui"] = True

        renderer.seed_dense_layout_authority(tracks)
        authority = renderer._dense_slot_authority

        self.assertNotEqual(
            (
                authority["dense_a"]["side"],
                authority["dense_a"]["slot_index"],
            ),
            (
                authority["dense_b"]["side"],
                authority["dense_b"]["slot_index"],
            ),
        )
        self.assertEqual(
            (
                authority["dense_a"]["side"],
                authority["dense_a"]["slot_index"],
            ),
            (
                authority["dense_c"]["side"],
                authority["dense_c"]["slot_index"],
            ),
        )
        self.assertEqual(authority["dense_b"]["slot_count"], 2)

    def test_dense_layout_authority_preserves_source_cluster_side_and_y_order(self) -> None:
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        tracks = [
            _track(
                text_id=text_id,
                start_frame=100,
                end_frame=200,
                geometry={"x": 0.14, "y": y, "width": 0.12, "height": 0.05},
                kind="ui",
                roles=["ui_chip"],
                simultaneous_count=4,
            )
            for text_id, y in (
                ("bottom", 0.70),
                ("top", 0.15),
                ("lower_middle", 0.55),
                ("upper_middle", 0.35),
            )
        ]
        for track in tracks:
            track["render_policy"]["context"]["dense_ui"] = True

        renderer.seed_dense_layout_authority(tracks)
        authority = renderer._dense_slot_authority

        self.assertEqual(
            {str(row["side"]) for row in authority.values()},
            {"left"},
        )
        self.assertEqual(authority["top"]["slot_index"], 0)
        self.assertEqual(authority["upper_middle"]["slot_index"], 1)
        self.assertEqual(authority["lower_middle"]["slot_index"], 2)
        self.assertEqual(authority["bottom"]["slot_index"], 3)
        self.assertEqual(
            {int(row["slot_count"]) for row in authority.values()},
            {4},
        )

    def test_hardsub_mask_expands_beyond_bright_core_to_cover_outline(self) -> None:
        frame = np.full((200, 400, 3), 50, dtype=np.uint8)
        frame[160:180, 150:250] = 255
        track = _track(
            geometry={"x": 0.35, "y": 0.75, "width": 0.30, "height": 0.15}
        )
        mask = _default_mask_builder(frame, track)
        self.assertEqual(int(mask[156, 200]), 255)

    def test_seeded_representative_mask_is_used_on_first_rendered_frame(self) -> None:
        frame = np.full((240, 400, 3), 150, dtype=np.uint8)
        seeded = _mask_builder(frame, _track())
        seeded[190:195, 136:139] = 255
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_mask("sub_a", seeded)
        _output, qa = renderer.render_frame(frame, [_track()])
        self.assertEqual(qa["tracks"][0]["mask"]["source"], "preseed_plus_sampling")
        self.assertGreater(
            qa["tracks"][0]["mask"]["metrics"]["mask_pixels"],
            int(np.count_nonzero(_mask_builder(frame, _track()))),
        )

    def test_dense_representative_union_falls_back_to_dynamic_frame_masks(self) -> None:
        frame = np.full((240, 400, 3), 150, dtype=np.uint8)
        track = _track()
        roi = track["render_policy"]["cover"]["roi"]
        dense_seed = np.zeros(frame.shape[:2], dtype=np.uint8)
        x0 = int(round(roi["x"] * frame.shape[1]))
        y0 = int(round(roi["y"] * frame.shape[0]))
        x1 = int(round((roi["x"] + roi["width"]) * frame.shape[1]))
        y1 = int(round((roi["y"] + roi["height"]) * frame.shape[0]))
        dense_seed[y0:y1, x0:x1] = 255
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_mask("sub_a", dense_seed)

        _first, first_qa = renderer.render_frame(frame, [track])
        _second, second_qa = renderer.render_frame(frame, [track])

        self.assertEqual(first_qa["status"], "PASS")
        self.assertEqual(
            first_qa["tracks"][0]["mask"]["source"],
            "track_sampling_dense_preseed_rejected",
        )
        self.assertEqual(
            second_qa["tracks"][0]["mask"]["source"],
            "track_sampling_dynamic",
        )

    def test_renders_cover_and_text_with_one_center_authority(self) -> None:
        frame = np.full((360, 640, 3), 90, dtype=np.uint8)
        frame[280:300, 250:390] = 240
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        track = _track(kind="ui", roles=["ui_chip"])
        output, qa = renderer.render_frame(frame, [track])

        self.assertEqual(output.shape, frame.shape)
        self.assertEqual(qa["status"], "PASS")
        track_qa = qa["tracks"][0]
        self.assertEqual(track_qa["mask"]["status"], "PASS")
        self.assertEqual(track_qa["damage"]["status"], "PASS")
        safe = track_qa["layout"]["safe_area"]
        cover = track_qa["cover_roi"]
        self.assertAlmostEqual(
            safe["x"] + safe["width"] * 0.5,
            cover["x"] + cover["width"] * 0.5,
            places=6,
        )
        self.assertAlmostEqual(
            safe["y"] + safe["height"] * 0.5,
            cover["y"] + cover["height"] * 0.5,
            places=6,
        )

    def test_dense_hardsub_uses_cover_aligned_layout_not_responsive_grid(self) -> None:
        frame = np.full((720, 1280, 3), 60, dtype=np.uint8)
        track = _track(simultaneous_count=12)
        cover = dict(track["render_policy"]["cover"]["roi"])
        track["render_policy"]["layout"].update(
            {"mode": "cover_aligned", "safe_area": cover}
        )
        track["render_policy"]["cover"]["mask_mode"] = "full_roi_plate"
        renderer = AdaptiveFrameRenderer(fontfile=_font())

        _output, qa = renderer.render_frame(frame, [track])

        self.assertEqual(qa["layout_mode"], "cover_aligned")
        self.assertEqual(qa["tracks"][0]["layout"]["placement_mode"], "cover_aligned")
        self.assertEqual(qa["tracks"][0]["layout"]["safe_area"], cover)

    def test_empty_mask_blocks_instead_of_silently_burning(self) -> None:
        frame = np.full((200, 300, 3), 100, dtype=np.uint8)

        def empty(source: np.ndarray, track: dict) -> np.ndarray:
            return np.zeros(source.shape[:2], dtype=np.uint8)

        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=empty)
        with self.assertRaises(AdaptiveRenderBlocked):
            renderer.render_frame(frame, [_track()])

    def test_stylized_title_dense_mask_requires_and_uses_reference_plate(self) -> None:
        clean = np.full((300, 500, 3), 130, dtype=np.uint8)
        titled = clean.copy()
        titled[100:160, 150:350] = (20, 20, 220)

        def filled(source: np.ndarray, track: dict) -> np.ndarray:
            mask = np.zeros(source.shape[:2], dtype=np.uint8)
            roi = track["render_policy"]["cover"]["roi"]
            height, width = source.shape[:2]
            x0 = int(round(roi["x"] * width))
            y0 = int(round(roi["y"] * height))
            x1 = int(round((roi["x"] + roi["width"]) * width))
            y1 = int(round((roi["y"] + roi["height"]) * height))
            mask[y0:y1, x0:x1] = 255
            return mask

        title = _track(
            geometry={"x": 0.30, "y": 0.33, "width": 0.40, "height": 0.20},
            kind="title",
            roles=["title"],
            text_vi="Tiêu đề",
        )
        title["render_policy"]["cover"].update(
            {
                "strategy": "adaptive_temporal_ink",
                "mask_mode": "stylized_components",
                "consistency_policy": "",
            }
        )
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=filled)
        renderer.seed_reference("sub_a", clean)
        _output, qa = renderer.render_frame(titled, [title])
        self.assertEqual(qa["status"], "PASS")
        self.assertEqual(qa["tracks"][0]["mask"]["fallback"], "reference_plate")

    def test_editor_caption_stylized_mask_does_not_require_reference_plate(self) -> None:
        frame = np.full((300, 500, 3), 130, dtype=np.uint8)

        def filled(source: np.ndarray, track: dict) -> np.ndarray:
            mask = np.zeros(source.shape[:2], dtype=np.uint8)
            roi = track["render_policy"]["cover"]["roi"]
            height, width = source.shape[:2]
            x0 = int(round(roi["x"] * width))
            y0 = int(round(roi["y"] * height))
            x1 = int(round((roi["x"] + roi["width"]) * width))
            y1 = int(round((roi["y"] + roi["height"]) * height))
            mask[y0:y1, x0:x1] = 255
            return mask

        caption = _track()
        caption["render_policy"]["cover"]["mask_mode"] = (
            "editor_caption_stylized_components"
        )
        caption["render_policy"]["context"][
            "editor_caption_residual_remediation"
        ] = True
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=filled)
        _output, qa = renderer.render_frame(frame, [caption])
        self.assertEqual(qa["status"], "PASS")
        self.assertNotEqual(qa["tracks"][0]["mask"]["fallback"], "reference_plate")

    def test_verified_output_template_uses_bounded_mask_not_reference_alignment(self) -> None:
        frame = np.full((720, 1280, 3), 130, dtype=np.uint8)
        track = _track(
            text_id="verified_micro",
            geometry={"x": 0.49, "y": 0.84, "width": 0.025, "height": 0.025},
            kind="ui",
            roles=["ui_chip"],
            text_vi="0 g",
        )
        track["output_residual_coverage"] = {
            "status": "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED"
        }
        track["render_policy"]["cover"]["mask_mode"] = "stylized_components"
        track["render_policy"]["context"].update(
            {
                "micro_ui": True,
                "output_residual_micro_ui_reference": True,
                "output_residual_bounded_dense_mask": True,
            }
        )
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_reference("verified_micro", np.full_like(frame, 20))
        _output, qa = renderer.render_frame(frame, [track])
        self.assertNotEqual(qa["tracks"][0]["mask"]["fallback"], "reference_plate")

    def test_ephemeral_intro_title_keeps_unified_spatial_cover(self) -> None:
        frame = np.full((300, 500, 3), 130, dtype=np.uint8)

        def filled(source: np.ndarray, track: dict) -> np.ndarray:
            mask = np.zeros(source.shape[:2], dtype=np.uint8)
            roi = track["render_policy"]["cover"]["roi"]
            height, width = source.shape[:2]
            x0 = int(round(roi["x"] * width))
            y0 = int(round(roi["y"] * height))
            x1 = int(round((roi["x"] + roi["width"]) * width))
            y1 = int(round((roi["y"] + roi["height"]) * height))
            mask[y0:y1, x0:x1] = 255
            return mask

        title = _track(
            start_frame=0,
            end_frame=3,
            geometry={"x": 0.30, "y": 0.33, "width": 0.40, "height": 0.20},
            kind="title",
            roles=["title"],
            text_vi="Tiêu đề",
        )
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=filled)
        _output, qa = renderer.render_frame(frame, [title])

        self.assertEqual(qa["status"], "PASS")
        self.assertEqual(
            qa["tracks"][0]["mask"]["fallback"], "full_roi_plate"
        )
        self.assertEqual(
            qa["tracks"][0]["temporal"]["mode"], "spatial_telea_r9"
        )

    def test_dense_caption_panel_is_allowed_inside_its_damage_budget(self) -> None:
        frame = np.full((400, 600, 3), 130, dtype=np.uint8)

        def filled(source: np.ndarray, track: dict) -> np.ndarray:
            mask = np.zeros(source.shape[:2], dtype=np.uint8)
            roi = track["render_policy"]["cover"]["roi"]
            height, width = source.shape[:2]
            x0 = int(round(roi["x"] * width))
            y0 = int(round(roi["y"] * height))
            x1 = int(round((roi["x"] + roi["width"]) * width))
            y1 = int(round((roi["y"] + roi["height"]) * height))
            mask[y0:y1, x0:x1] = 255
            return mask

        caption = _track(
            geometry={"x": 0.10, "y": 0.60, "width": 0.60, "height": 0.04},
            kind="ui",
            roles=["generic"],
            text_vi="Phá»¥ Ä‘á» má»™t dÃ²ng",
        )
        caption["render_policy"]["context"]["caption_row"] = True
        caption["render_policy"]["context"]["typography_kind"] = "caption_row"
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=filled)

        _output, qa = renderer.render_frame(frame, [caption])

        self.assertEqual(qa["status"], "PASS")
        self.assertEqual(qa["tracks"][0]["mask"]["fallback"], "full_roi_plate")

    def test_temporal_state_is_reused_on_next_static_frame(self) -> None:
        frame = np.full((240, 400, 3), 150, dtype=np.uint8)
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        track = _track()
        track["render_policy"]["cover"].update(
            {
                "strategy": "adaptive_temporal_ink",
                "mask_mode": "ink_components",
                "consistency_policy": "",
            }
        )
        renderer.render_frame(frame, [track])
        _output, qa = renderer.render_frame(frame, [track])
        self.assertEqual(qa["tracks"][0]["temporal"]["mode"], "static_plate")

    def test_static_overlay_mask_is_sampled_then_cached_per_track(self) -> None:
        frame = np.full((240, 400, 3), 150, dtype=np.uint8)
        calls = 0

        def counted(source: np.ndarray, track: dict) -> np.ndarray:
            nonlocal calls
            calls += 1
            return _mask_builder(source, track)

        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=counted)
        track = _track()
        modes = []
        for _ in range(7):
            _output, qa = renderer.render_frame(frame, [track])
            modes.append(qa["tracks"][0]["mask"]["source"])
        self.assertEqual(calls, 3)
        self.assertEqual(modes[-1], "track_cache")

    def test_dense_tracks_keep_cover_aligned_layout(self) -> None:
        frame = np.full((720, 1280, 3), 60, dtype=np.uint8)
        tracks = []
        for index in range(8):
            x = 0.05 if index < 4 else 0.75
            tracks.append(
                _track(
                    text_id=f"t{index}",
                    content_id=f"c{index}",
                    geometry={"x": x, "y": 0.1 + (index % 4) * 0.18, "width": 0.15, "height": 0.05},
                    kind="ui",
                    roles=["ui_chip"],
                    text_vi=f"Nhãn {index}",
                    simultaneous_count=8,
                )
            )
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        _output, qa = renderer.render_frame(frame, tracks)
        self.assertEqual(qa["status"], "PASS")
        self.assertEqual(qa["layout_mode"], "cover_aligned")
        self.assertEqual(len(qa["dense_layouts"]), 0)
        self.assertTrue(
            all(
                row["layout"]["placement_mode"] == "cover_aligned"
                for row in qa["tracks"]
            )
        )

    def test_dense_ui_empty_ink_uses_bounded_tight_roi_fallback(self) -> None:
        frame = np.full((400, 600, 3), 90, dtype=np.uint8)

        def empty(source: np.ndarray, track: dict) -> np.ndarray:
            return np.zeros(source.shape[:2], dtype=np.uint8)

        tracks = [
            _track(
                text_id=f"dense_{index}",
                content_id=f"dense_content_{index}",
                geometry={
                    "x": 0.05 if index < 4 else 0.75,
                    "y": 0.08 + (index % 4) * 0.2,
                    "width": 0.12,
                    "height": 0.04,
                },
                kind="ui",
                roles=["ui_chip"],
                text_vi=f"Giá trị {index}",
                simultaneous_count=8,
            )
            for index in range(8)
        ]
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=empty)
        _output, qa = renderer.render_frame(frame, tracks)
        self.assertEqual(qa["status"], "PASS")
        self.assertTrue(
            all(row["mask"]["fallback"] == "tight_roi" for row in qa["tracks"])
        )

    def test_ephemeral_micro_ui_empty_ink_uses_bounded_tight_roi(self) -> None:
        frame = np.full((400, 600, 3), 90, dtype=np.uint8)

        def empty(source: np.ndarray, track: dict) -> np.ndarray:
            return np.zeros(source.shape[:2], dtype=np.uint8)

        track = _track(
            text_id="micro_01",
            content_id="micro_content_01",
            geometry={"x": 0.45, "y": 0.90, "width": 0.025, "height": 0.03},
            kind="ui",
            roles=["ui_chip"],
            text_vi="Hoàn thành",
            simultaneous_count=1,
        )
        track["start_frame"] = 4
        track["end_frame"] = 6
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=empty)

        _output, qa = renderer.render_frame(frame, [track])

        self.assertEqual(qa["status"], "PASS")
        self.assertEqual(
            qa["tracks"][0]["mask"]["fallback"], "micro_ui_tight_roi"
        )

    def test_overlapping_same_content_covers_both_but_draws_once(self) -> None:
        frame = np.full((400, 600, 3), 90, dtype=np.uint8)
        first = _track(
            text_id="dup_large",
            content_id="same_content",
            geometry={"x": 0.1, "y": 0.7, "width": 0.5, "height": 0.06},
            kind="ui",
            text_vi="Một nhãn",
            simultaneous_count=2,
        )
        second = _track(
            text_id="dup_small",
            content_id="same_content",
            geometry={"x": 0.2, "y": 0.71, "width": 0.2, "height": 0.04},
            kind="ui",
            text_vi="Một nhãn",
            simultaneous_count=2,
        )
        renderer = AdaptiveFrameRenderer(
            fontfile=_font(), mask_builder=_mask_builder
        )

        _output, qa = renderer.render_frame(frame, [first, second])

        layouts = [row for row in qa["tracks"] if "layout" in row]
        suppressed = [
            row for row in qa["tracks"] if row.get("text_render_suppressed")
        ]
        self.assertEqual(len(layouts), 1)
        self.assertEqual(len(suppressed), 1)

    def test_dense_panel_plate_is_stable_and_deduplicates_to_twelve_lines(self) -> None:
        frame = np.full((240, 400, 3), 120, dtype=np.uint8)
        panel = {
            "panel_id": "panel_1", "start_frame": 2, "end_frame": 10,
            "panel_roi": {"x": 0.1, "y": 0.05, "width": 0.4, "height": 0.8},
            "max_frame_change_fraction": 0.55, "max_rendered_lines": 12,
        }
        tracks = [
            _track(text_id=f"p{i}", content_id=f"c{i%10}",
                   geometry={"x": 0.15, "y": 0.08 + (i % 8) * 0.08, "width": 0.1, "height": 0.03},
                   kind="ui", roles=["ui_chip"], text_vi=f"kcal {i}", simultaneous_count=20)
            for i in range(20)
        ]
        for row in tracks:
            row["render_policy"]["context"]["dense_ui"] = True
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], tracks, plate_colors={"panel_1": [20, 30, 40]})
        first, qa = renderer.render_frame(frame, tracks, frame_index=2)
        second, qa2 = renderer.render_frame(frame, tracks, frame_index=3)
        self.assertEqual(qa["layout_mode"], "dense_ui_panel")
        self.assertLessEqual(len(qa["dense_ui_panels"][0]["layouts"]), 12)
        self.assertEqual(qa["dense_ui_panels"][0]["plate_bgr"], [20, 30, 40])
        self.assertTrue(np.array_equal(first, second))

    def test_dense_panel_deduplicates_same_vietnamese_across_content_ids(self) -> None:
        panel = {
            "panel_id": "panel_text_dedup", "start_frame": 0, "end_frame": 20,
            "panel_roi": {"x": 0.1, "y": 0.05, "width": 0.4, "height": 0.8},
            "max_frame_change_fraction": 0.55, "max_rendered_lines": 12,
        }
        tracks = [
            _track(text_id="a", content_id="content_a", text_vi="Dầu đậu phộng 45 kcal/5.00 ml", start_frame=0, end_frame=20),
            _track(text_id="b", content_id="content_b", text_vi="  dầu đậu phộng 45 KCAL/5.00 ML  ", start_frame=0, end_frame=20),
        ]
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], tracks, plate_colors={"panel_text_dedup": [1, 2, 3]})
        self.assertEqual(len(renderer._dense_ui_panel_tracks["panel_text_dedup"]), 1)

    def test_dense_panel_prefers_full_label_and_suppresses_external_duplicate(self) -> None:
        frame = np.full((720, 1280, 3), 120, dtype=np.uint8)
        panel = {
            "panel_id": "panel_full", "start_frame": 0, "end_frame": 20,
            "panel_roi": {"x": 0.1, "y": 0.05, "width": 0.4, "height": 0.8},
            "max_frame_change_fraction": 0.55, "max_rendered_lines": 12,
        }
        short = _track(text_id="short", content_id="potato", text_vi="205 kcal/253.00 g",
                       start_frame=0, end_frame=20, simultaneous_count=20)
        full = _track(text_id="full", content_id="potato", text_vi="Khoai tây 205 kcal/253.00 g",
                      geometry={"x": 0.51, "y": 0.4, "width": 0.08, "height": 0.03},
                      start_frame=0, end_frame=20, simultaneous_count=20)
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], [short, full], plate_colors={"panel_full": [1, 2, 3]})
        self.assertEqual(renderer._dense_ui_panel_tracks["panel_full"][0]["text_id"], "full")
        _output, qa = renderer.render_frame(frame, [short, full], frame_index=1)
        full_qa = next(row for row in qa["tracks"] if row.get("text_id") == "full")
        self.assertEqual(full_qa["text_render_suppressed"], "deduplicated_by_dense_ui_panel")

    def test_dense_panel_drops_metric_fragment_when_full_label_exists(self) -> None:
        panel = {
            "panel_id": "panel_metric", "start_frame": 0, "end_frame": 20,
            "panel_roi": {"x": 0.1, "y": 0.05, "width": 0.4, "height": 0.8},
            "max_frame_change_fraction": 0.55, "max_rendered_lines": 12,
        }
        tracks = [
            _track(text_id="fragment", content_id="metric_only", text_vi="343 kcal/235.00 g", start_frame=0, end_frame=20),
            _track(text_id="named", content_id="chicken", text_vi="Đùi gà 343 kcal/235.00 g", start_frame=0, end_frame=20),
            _track(text_id="egg_fragment", content_id="egg_metric", text_vi="120 kcal/86.00 g", start_frame=0, end_frame=20),
            _track(text_id="egg_named", content_id="egg", text_vi="Trứng 120 kcal/86.00 g", start_frame=0, end_frame=20),
        ]
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], tracks, plate_colors={"panel_metric": [1, 2, 3]})
        assert {row["text_id"] for row in renderer._dense_ui_panel_tracks["panel_metric"]} == {"named", "egg_named"}

    def test_dense_panel_releases_last_four_frames_to_avoid_boundary_flicker(self) -> None:
        frame = np.full((120, 200, 3), 120, dtype=np.uint8)
        panel = {"panel_id": "panel_1", "start_frame": 2, "end_frame": 10,
                 "panel_roi": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3},
                 "max_frame_change_fraction": 0.55, "max_rendered_lines": 12,
                 "temporal_exit_release_frames": 4}
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], [], plate_colors={"panel_1": [1, 2, 3]})
        output, qa = renderer.render_frame(frame, [], frame_index=7)
        self.assertTrue(np.array_equal(output, frame))
        self.assertTrue(qa["dense_ui_panels"][0]["temporal_exit_release"])

    def test_dense_panel_is_inactive_outside_approved_span(self) -> None:
        frame = np.full((120, 200, 3), 120, dtype=np.uint8)
        panel = {"panel_id": "panel_1", "start_frame": 2, "end_frame": 4,
                 "panel_roi": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3},
                 "max_frame_change_fraction": 0.55, "max_rendered_lines": 12}
        renderer = AdaptiveFrameRenderer(fontfile=_font(), mask_builder=_mask_builder)
        renderer.seed_dense_ui_panels([panel], [_track(text_vi="Nhãn")], plate_colors={"panel_1": [1, 2, 3]})
        output, qa = renderer.render_frame(frame, [], frame_index=1)
        self.assertTrue(np.array_equal(output, frame))
        self.assertEqual(qa["layout_mode"], "idle")


if __name__ == "__main__":
    unittest.main()
