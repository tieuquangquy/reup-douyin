from __future__ import annotations

import numpy as np

from src.media_pipeline.frame_sampling.coverage_track_closure import (
    COVERAGE_TRACK_POLICY_VERSION,
    CoverageTrackClosure,
)


def _frame(with_text: bool, *, x: int = 24) -> np.ndarray:
    frame = np.full((90, 160, 3), 70, dtype=np.uint8)
    if with_text:
        for offset in range(0, 72, 12):
            frame[52:66, x + offset : x + offset + 5] = 245
            frame[57:60, x + offset : x + offset + 10] = 245
    return frame


def test_closure_keeps_a_single_frame_flash_blocking_authority() -> None:
    closure = CoverageTrackClosure(
        [
            {
                "text_id": "sub_01",
                "start_frame": 5,
                "end_frame": 5,
                "hit_frames": [5],
                "box_coords": [20, 48, 110, 70],
            }
        ],
        source_width=160,
        source_height=90,
        fps=30.0,
    )
    for index in range(12):
        closure.observe(_frame(index == 5), frame_index=index)
    payload = closure.finalize(frame_count=12)
    track = payload["tracks"][0]
    assert track["policy_version"] == COVERAGE_TRACK_POLICY_VERSION
    assert any(start <= 5 <= end for start, end in track["presence_ranges"])


def test_closure_geometry_expands_when_text_moves_outside_seed_box() -> None:
    closure = CoverageTrackClosure(
        [
            {
                "text_id": "sub_01",
                "start_frame": 3,
                "end_frame": 5,
                "hit_frames": [3, 5],
                "box_coords": [30, 48, 92, 70],
            }
        ],
        source_width=160,
        source_height=90,
        fps=30.0,
    )
    for index in range(9):
        closure.observe(
            _frame(index in {3, 4, 5}, x=18 if index == 4 else 30),
            frame_index=index,
        )
    track = closure.finalize(frame_count=9)["tracks"][0]
    assert track["geometry_keyframes"]
    assert min(
        row["geometry"]["x"] for row in track["geometry_keyframes"]
    ) < 30 / 160


def test_closure_records_textness_that_has_no_seed_track() -> None:
    closure = CoverageTrackClosure(
        [], source_width=160, source_height=90, fps=30.0
    )
    for index in range(8):
        closure.observe(_frame(index == 4), frame_index=index)
    payload = closure.finalize(frame_count=8)
    assert 4 in payload["unassigned_candidate_frames"]
    assert any(
        row["frame_index"] == 4 for row in payload["unassigned_candidates"]
    )


def test_closure_does_not_report_owned_text_as_unassigned() -> None:
    closure = CoverageTrackClosure(
        [
            {
                "text_id": "sub_01",
                "start_frame": 4,
                "end_frame": 4,
                "hit_frames": [4],
                "box_coords": [16, 44, 125, 74],
            }
        ],
        source_width=160,
        source_height=90,
        fps=30.0,
    )
    for index in range(8):
        closure.observe(_frame(index == 4), frame_index=index)
    payload = closure.finalize(frame_count=8)
    assert 4 not in payload["unassigned_candidate_frames"]


def test_closure_records_saturated_outlined_title_discovery() -> None:
    frame = np.full((180, 320, 3), 85, dtype=np.uint8)
    # Four title glyph blocks with yellow fill and a dark outline.  This
    # synthetic row models the colour/outline case that grayscale proxy
    # textness alone can under-rank.
    for x in (72, 116, 160, 204):
        frame[104:142, x - 4 : x + 32] = 10
        frame[110:136, x : x + 28] = (0, 220, 245)

    closure = CoverageTrackClosure(
        [], source_width=320, source_height=180, fps=30.0
    )
    closure.observe(frame, frame_index=0)
    payload = closure.finalize(frame_count=1)

    assert 0 in payload["unassigned_candidate_frames"]
    assert any(
        row["frame_index"] == 0
        and row["geometry"]["y"] >= 0.45
        and row["geometry"]["width"] >= 0.30
        for row in payload["unassigned_candidates"]
    )
