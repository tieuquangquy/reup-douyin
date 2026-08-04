from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import cv2

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    DetectionHit,
    MergedTrack,
    TemporalVisualProbe,
    bound_dense_rescan_frame_indices,
    classify_visual_text_provenance,
    dense_source_ui_panel_member_ids,
    filter_tracks_by_local_text,
    interval_dense_rescan_frame_indices,
)
from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    build_phase2_contract,
    build_phase2_handoff,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    build_phase4_render_input,
)
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    scan_full_timeline_visual_authority,
)


def _track(
    box: tuple[float, float, float, float],
    *,
    start: int = 0,
    end: int = 12,
    hits: int = 8,
) -> MergedTrack:
    cx = (box[0] + box[2]) * 0.5
    cy = (box[1] + box[3]) * 0.5
    return MergedTrack(
        start_frame=start,
        end_frame=end,
        box_coords=list(box),
        best_frame_index=start,
        best_sharpness=10.0,
        centroid=(cx, cy),
        hit_count=hits,
        hit_boxes=[box for _ in range(hits)],
        hit_frames=list(range(start, start + hits)),
        hit_sharpness=[10.0 for _ in range(hits)],
    )


def test_temporal_probe_guarantees_a_heavy_frame_in_every_three_frame_flash() -> None:
    probe = TemporalVisualProbe(max_gap_frames=3)
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    heavy = [probe.inspect(frame, frame_index=index)[0] for index in range(12)]

    for start in range(10):
        assert any(heavy[start : start + 3])


def test_temporal_probe_adds_transition_between_baselines() -> None:
    probe = TemporalVisualProbe(max_gap_frames=3)
    black = np.zeros((120, 80, 3), dtype=np.uint8)
    changed = black.copy()
    changed[30:90, 10:70] = 255

    assert probe.inspect(black, frame_index=0)[0]
    should_probe, reason = probe.inspect(changed, frame_index=1)
    assert should_probe
    assert reason in {"luma_transition", "edge_transition"}


def test_provenance_protects_dense_compact_source_panel_but_keeps_hardsub() -> None:
    phone_tracks = [
        _track((100.0, 320.0, 145.0, 346.0)),
        _track((175.0, 330.0, 220.0, 356.0)),
        _track((115.0, 395.0, 160.0, 421.0)),
        _track((190.0, 405.0, 235.0, 431.0)),
    ]
    hardsub = _track((500.0, 850.0, 1400.0, 920.0))
    tracks = [*phone_tracks, hardsub]

    classified = classify_visual_text_provenance(
        tracks,
        frame_w=1920,
        frame_h=1080,
        text_audit={},
    )

    assert {
        classified[id(track)]["classification"] for track in phone_tracks
    } == {"SOURCE_INTRINSIC"}
    assert classified[id(hardsub)]["classification"] == "EDITOR_OVERLAY"


def test_phone_app_plane_propagates_source_provenance_to_wide_ui_labels() -> None:
    phone_tracks = [
        _track(
            (120.0 + column * 510.0, 1320.0 + row * 560.0,
             390.0 + column * 510.0, 1390.0 + row * 560.0),
            start=778,
            end=823,
            hits=40,
        )
        for row in range(4)
        for column in range(4)
    ]
    editor_hardsub = _track(
        (120.0, 3540.0, 1660.0, 3650.0),
        start=778,
        end=823,
        hits=40,
    )
    tracks = [*phone_tracks, editor_hardsub]

    panel_ids = dense_source_ui_panel_member_ids(
        tracks, frame_w=2160, frame_h=3840
    )
    classified = classify_visual_text_provenance(
        tracks,
        frame_w=2160,
        frame_h=3840,
        text_audit={},
    )

    assert {id(track) for track in phone_tracks} <= panel_ids
    assert {
        classified[id(track)]["classification"] for track in phone_tracks
    } == {"SOURCE_INTRINSIC"}
    assert classified[id(editor_hardsub)]["classification"] == "EDITOR_OVERLAY"


def test_phone_app_plane_propagates_to_joined_row_but_not_tall_editor_caption() -> None:
    phone_cells = [
        _track(
            (
                120.0 + column * 510.0,
                1020.0 + row * 520.0,
                360.0 + column * 510.0,
                1080.0 + row * 520.0,
            ),
            start=778,
            end=823,
            hits=40,
        )
        for row in range(4)
        for column in range(4)
    ]
    joined_source_row = _track(
        (110.0, 2480.0, 2050.0, 2540.0),
        start=778,
        end=823,
        hits=40,
    )
    tall_editor_caption = _track(
        (480.0, 1840.0, 1680.0, 1980.0),
        start=778,
        end=823,
        hits=40,
    )
    tracks = [*phone_cells, joined_source_row, tall_editor_caption]

    classified = classify_visual_text_provenance(
        tracks,
        frame_w=2160,
        frame_h=3840,
        text_audit={},
    )

    assert classified[id(joined_source_row)]["classification"] == "SOURCE_INTRINSIC"
    assert (
        "dense_source_ui_context_propagation"
        in classified[id(joined_source_row)]["reasons"]
    )
    assert classified[id(tall_editor_caption)]["classification"] == "EDITOR_OVERLAY"


def test_repeated_phone_ui_row_overrides_hardsub_shape_without_absorbing_caption() -> None:
    phone_cells = [
        _track(
            (
                120.0 + column * 510.0,
                980.0 + row * 520.0,
                360.0 + column * 510.0,
                1040.0 + row * 520.0,
            ),
            start=100,
            end=145,
            hits=40,
        )
        for row in range(4)
        for column in range(4)
    ]
    repeated_row = [
        _track(
            (126.0, 3338.0, 1308.0, 3582.0),
            start=170 + index * 8,
            end=172 + index * 8,
            hits=3,
        )
        for index in range(8)
    ]
    adjacent_source_fragment = _track(
        (780.0, 3340.0, 1300.0, 3460.0),
        start=146,
        end=165,
        hits=20,
    )
    editor_caption = _track(
        (180.0, 3340.0, 1020.0, 3430.0),
        start=170,
        end=220,
        hits=40,
    )
    tracks = [
        *phone_cells,
        adjacent_source_fragment,
        *repeated_row,
        editor_caption,
    ]

    classified = classify_visual_text_provenance(
        tracks,
        frame_w=2160,
        frame_h=3840,
        text_audit={},
    )

    assert {
        classified[id(track)]["classification"] for track in repeated_row
    } == {"SOURCE_INTRINSIC"}
    assert (
        classified[id(adjacent_source_fragment)]["classification"]
        == "SOURCE_INTRINSIC"
    )
    assert classified[id(editor_caption)]["classification"] == "EDITOR_OVERLAY"


def test_interval_dense_rescan_does_not_expand_a_stable_title_to_every_frame() -> None:
    hits = [
        DetectionHit(
            frame_index=frame_index,
            box_xyxy=(300.0, 800.0, 1200.0, 900.0),
            sharpness=10.0,
        )
        for frame_index in range(0, 120, 3)
    ]

    wanted = interval_dense_rescan_frame_indices(
        hits,
        step=1,
        frame_count=120,
        frame_w=1920,
        frame_h=1080,
        max_centroid_px=20.0,
        max_probe_gap_frames=3,
    )

    assert len(wanted) <= 8
    assert 0 in wanted
    assert 118 in wanted


def test_production_text_gate_retains_dense_source_panel_for_provenance() -> None:
    phone_tracks = [
        _track(
            (120.0 + column * 510.0, 1320.0 + row * 560.0,
             390.0 + column * 510.0, 1390.0 + row * 560.0),
            start=778,
            end=823,
            hits=40,
        )
        for row in range(4)
        for column in range(4)
    ]

    kept, audit = filter_tracks_by_local_text(
        phone_tracks,
        frame_cache={},
        frame_w=2160,
        frame_h=3840,
        recognizer=None,
        preserve_source_candidates=True,
    )

    assert len(kept) == len(phone_tracks)
    assert audit["dense_source_panel_candidates"] == len(phone_tracks)
    assert audit["preserved_source_candidates"] == len(phone_tracks)
    assert {
        getattr(track, "_source_intrinsic_candidate", None) for track in kept
    } == {"dense_source_ui_panel"}


def test_dense_rescan_budget_cannot_recreate_full_duration_scan() -> None:
    selected, audit = bound_dense_rescan_frame_indices(
        list(range(100)),
        already_scanned=list(range(0, 100, 4)),
        frame_count=100,
    )

    assert len(set(selected) | set(range(0, 100, 4))) <= 48
    assert audit["guard_triggered"] is True


def test_phase2_handoff_carries_protected_source_without_render_geometry() -> None:
    with TemporaryDirectory() as temp_dir:
        timeline_path = Path(temp_dir) / "master_timeline.json"
        timeline_path.write_text("[]", encoding="utf-8")
        timeline = [
            {
                "text_id": "editor_01",
                "start_frame": 0,
                "end_frame": 5,
                "box_coords": [100.0, 800.0, 800.0, 900.0],
                "ocr_text": "午餐",
                "visual_provenance": {"classification": "EDITOR_OVERLAY"},
            }
        ]
        protected = [
            {
                "text_id": "phone_01",
                "start_frame": 0,
                "end_frame": 5,
                "box_coords": [100.0, 100.0, 300.0, 300.0],
                "action": "PRESERVE_SOURCE_PIXELS",
            }
        ]
        initial = build_phase2_contract(
            timeline,
            phase1_timeline_path=timeline_path,
            provider_mode="local",
            model_version="ppocr-v5",
            protected_source_tracks=protected,
        )
        item = initial["content_objects"][0]
        approvals = {
            item["content_id"]: {
                "decision": "APPROVE",
                "ocr_text_approved": "午餐",
                "review_input_sha256": item["review_input_sha256"],
            }
        }
        approved = build_phase2_contract(
            timeline,
            phase1_timeline_path=timeline_path,
            provider_mode="local",
            model_version="ppocr-v5",
            protected_source_tracks=protected,
            approvals=approvals,
        )
        phase2_path = Path(temp_dir) / "phase2_ocr_timeline.json"
        phase2_path.write_text(
            json.dumps(approved, ensure_ascii=False), encoding="utf-8"
        )
        handoff = build_phase2_handoff(
            approved, phase2_timeline_path=phase2_path
        )

        assert handoff["status"] == "READY_FOR_PHASE3"
        assert handoff["preserved_source_items"][0]["text_id"] == "phone_01"
        assert "phone_01" not in handoff["geometry_map"]


def test_phase4_excludes_protected_source_from_cover_and_overlay_authority() -> None:
    master = [
        {
            "text_id": "editor_01",
            "start_frame": 0,
            "end_frame": 5,
            "best_frame_index": 2,
            "box_coords": [100.0, 800.0, 800.0, 900.0],
        },
        {
            "text_id": "phone_01",
            "start_frame": 0,
            "end_frame": 5,
            "best_frame_index": 2,
            "box_coords": [100.0, 100.0, 300.0, 300.0],
            "visual_provenance": {"classification": "SOURCE_INTRINSIC"},
        },
    ]
    phase2 = {
        "track_enrichments": [
            {"text_id": "editor_01", "content_id": "content_01"}
        ],
        "content_objects": [
            {
                "content_id": "content_01",
                "roles": ["hardsub"],
                "ocr_text_raw_candidates": ["午餐"],
            }
        ],
    }
    phase3 = {
        "status": "READY_FOR_RENDER",
        "geometry_map": {
            "editor_01": {
                "content_id": "content_01",
                "text_vi": "Bữa trưa",
                "translation_status": "TRANSLATION_APPROVED",
            }
        },
    }

    result = build_phase4_render_input(
        master,
        phase2,
        phase3,
        video_metadata={
            "frame_width": 1920,
            "frame_height": 1080,
            "frame_count": 30,
            "fps": 30.0,
        },
        refs={},
        protected_source_refs=["phone_01"],
    )

    assert [row["text_id"] for row in result["render_tracks"]] == ["editor_01"]
    assert result["protected_source_tracks"][0]["text_id"] == "phone_01"
    assert result["protected_source_tracks"][0]["action"] == "PRESERVE_SOURCE_PIXELS"


def test_full_timeline_qa_catches_one_missing_edited_frame() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_path = root / "source.avi"
        rendered_path = root / "rendered.avi"
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        source_writer = cv2.VideoWriter(str(source_path), fourcc, 30.0, (96, 96))
        rendered_writer = cv2.VideoWriter(str(rendered_path), fourcc, 30.0, (96, 96))
        assert source_writer.isOpened() and rendered_writer.isOpened()
        try:
            for frame_index in range(6):
                source = np.zeros((96, 96, 3), dtype=np.uint8)
                rendered = source.copy()
                if frame_index in {1, 3}:  # frame 2 intentionally flashes source.
                    rendered[60:82, 20:76] = 255
                source_writer.write(source)
                rendered_writer.write(rendered)
        finally:
            source_writer.release()
            rendered_writer.release()
        contract = {
            "render_tracks": [
                {
                    "text_id": "editor",
                    "start_frame": 1,
                    "end_frame": 3,
                    "geometry": {
                        "x": 20 / 96,
                        "y": 60 / 96,
                        "width": 56 / 96,
                        "height": 22 / 96,
                    },
                }
            ],
            "protected_source_tracks": [
                {
                    "text_id": "phone",
                    "start_frame": 0,
                    "end_frame": 5,
                    "geometry": {
                        "x": 0.05,
                        "y": 0.05,
                        "width": 0.20,
                        "height": 0.20,
                    },
                }
            ],
        }

        result = scan_full_timeline_visual_authority(
            source_path, rendered_path, contract=contract
        )

        assert result["status"] == "BLOCKED"
        assert 2 in result["missing_edit_frames"]
        assert result["protected_source_damage_frames"] == []
