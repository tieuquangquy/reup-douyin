from __future__ import annotations

import pytest

from scripts.build_phase4_dense_ui_panel_proposal import (
    DenseUiPanelProposalError,
    panel_roi_from_detections,
    select_dense_epoch,
)


def _track(start: int, end: int, simultaneous: int = 30) -> dict:
    return {
        "text_id": f"p4out_{start}_{end}",
        "start_frame": start,
        "end_frame": end,
        "output_residual_coverage": {"status": "VERIFIED"},
        "render_policy": {
            "context": {"dense_ui": True, "simultaneous_count": simultaneous}
        },
    }


def test_selects_bounded_dense_epoch_covering_residuals() -> None:
    epoch, tracks = select_dense_epoch(
        {"render_tracks": [_track(10, 20), _track(15, 25), _track(200, 260)]},
        [17, 18],
    )
    assert epoch == [10, 25]
    assert len(tracks) == 2


def test_rejects_unbounded_or_unrelated_dense_epoch() -> None:
    with pytest.raises(DenseUiPanelProposalError):
        select_dense_epoch({"render_tracks": [_track(0, 200)]}, [100])


def test_panel_roi_is_padded_and_clamped() -> None:
    roi = panel_roi_from_detections(
        [
            {
                "frame_index": 10,
                "geometry": {"x": 0.01, "y": 0.02, "width": 0.1, "height": 0.1},
            },
            {
                "frame_index": 11,
                "geometry": {"x": 0.8, "y": 0.85, "width": 0.19, "height": 0.14},
            },
        ],
        frame_span=[10, 11],
    )
    assert roi == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
