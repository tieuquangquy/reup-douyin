from __future__ import annotations

from src.media_pipeline.frame_sampling.coverage_track_closure import (
    schedule_unassigned_discovery_frames,
)


def _candidate(frame: int, *, x: float, y: float, width: float = 0.30) -> dict:
    return {
        "frame_index": frame,
        "geometry": {"x": x, "y": y, "width": width, "height": 0.035},
        "ink_density": 0.20,
    }


def test_short_text_epoch_is_not_starved_by_full_duration_texture() -> None:
    candidates = [
        _candidate(frame, x=0.02, y=0.20, width=0.80)
        for frame in range(0, 300)
    ]
    candidates.extend(
        _candidate(frame, x=0.38, y=0.68, width=0.24)
        for frame in range(147, 153)
    )

    selected, audit = schedule_unassigned_discovery_frames(
        candidates,
        fps=30.0,
        duration_ms=10_000,
        max_frames=12,
    )

    assert any(147 <= frame <= 152 for frame in selected)
    assert audit["candidate_epochs"] >= 2
    assert audit["selected_frames"] <= 12


def test_isolated_one_frame_flash_keeps_its_frame() -> None:
    selected, _audit = schedule_unassigned_discovery_frames(
        [
            *[_candidate(frame, x=0.10, y=0.10) for frame in range(120)],
            _candidate(61, x=0.65, y=0.72, width=0.20),
        ],
        fps=30.0,
        duration_ms=4_000,
        max_frames=8,
    )

    assert 61 in selected


def test_opening_title_reserves_frame_zero_before_temporal_boundary_exists() -> None:
    candidates = [
        *[_candidate(frame, x=0.04, y=0.18, width=0.75) for frame in range(300)],
        *[_candidate(frame, x=0.20, y=0.70, width=0.58) for frame in range(0, 5)],
    ]

    selected, audit = schedule_unassigned_discovery_frames(
        candidates,
        fps=30.0,
        duration_ms=10_000,
        max_frames=8,
    )

    assert 0 in selected
    assert 0 in audit["edge_reserved_frames"]
    assert audit["selected_frames"] <= 8
