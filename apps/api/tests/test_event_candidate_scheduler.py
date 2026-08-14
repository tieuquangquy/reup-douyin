from __future__ import annotations

import numpy as np
from unittest.mock import patch

from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    EVENT_SCAN_ENGINE_VERSION,
    CandidateWindow,
    EventFrameScheduler,
    TileVisualChangeProbe,
    build_audio_candidate_windows,
    merge_candidate_windows,
)


def test_audio_windows_merge_and_expand_uncertain_boundaries() -> None:
    windows = build_audio_candidate_windows(
        [
            {"start_ms": 1_000, "end_ms": 1_700, "confidence": 1.0},
            {"start_ms": 1_800, "end_ms": 2_100, "confidence": 0.5},
        ],
        duration_ms=5_000,
    )
    assert len(windows) == 1
    assert windows[0].start_ms == 680
    assert windows[0].end_ms > 2_480
    assert windows[0].sources == ("AUDIO_GUIDED",)


def test_merge_candidate_windows_preserves_sources() -> None:
    merged = merge_candidate_windows(
        [
            CandidateWindow(0, 500, ("AUDIO_GUIDED",), 0.7),
            CandidateWindow(550, 900, ("VISUAL_TEXTNESS_CHANGE",), 0.9),
        ],
        duration_ms=1_000,
    )
    assert len(merged) == 1
    assert set(merged[0].sources) == {
        "AUDIO_GUIDED",
        "VISUAL_TEXTNESS_CHANGE",
    }
    assert merged[0].confidence == 0.9


def test_visual_probe_triggers_on_local_edge_change() -> None:
    probe = TileVisualChangeProbe(
        scene_threshold=0.95,
        local_edge_threshold=0.01,
        max_tile_edge_threshold=0.02,
    )
    stable = np.zeros((160, 160, 3), dtype=np.uint8)
    changed = stable.copy()
    changed[20:50, 15:145] = 255
    first = probe.inspect(stable)
    second = probe.inspect(changed)
    assert first.triggered is True
    assert second.triggered is True
    assert second.reason == "local_textness_change"


def test_scheduler_combines_audio_visual_burst_and_heartbeat() -> None:
    scheduler = EventFrameScheduler(
        fps=10.0,
        frame_count=50,
        duration_ms=5_000,
        audio_windows=[CandidateWindow(1_000, 2_000, ("AUDIO_GUIDED",), 1.0)],
        audio_sample_fps=2.0,
        heartbeat_fps=1.0,
        burst_sample_fps=5.0,
    )
    frame = np.zeros((120, 120, 3), dtype=np.uint8)
    selected: list[int] = []
    reasons: set[str] = set()
    for index in range(50):
        candidate = frame.copy()
        if index >= 25:
            candidate[10:35, 10:110] = 255
        use, why = scheduler.inspect(candidate, frame_index=index)
        if use:
            selected.append(index)
            reasons.update(why)
    payload = scheduler.payload(scanned_frames=len(selected))
    assert payload["engine_version"] == EVENT_SCAN_ENGINE_VERSION
    assert "audio_guided" in reasons
    assert "safety_heartbeat" in reasons
    assert "visual_burst" in reasons
    assert len(selected) < 30
    assert payload["heavy_probe_ratio"] < 0.6


def test_one_frame_textness_flash_bypasses_visual_cooldown() -> None:
    scheduler = EventFrameScheduler(
        fps=30.0,
        frame_count=12,
        duration_ms=400,
        heartbeat_fps=0.2,
        visual_trigger_cooldown_ms=900,
        max_detector_fps=2.0,
    )
    base = np.full((180, 320, 3), 72, dtype=np.uint8)
    selected: dict[int, tuple[str, ...]] = {}
    for index in range(12):
        frame = base.copy()
        if index == 5:
            for x in range(28, 284, 24):
                frame[124:148, x : x + 8] = 245
                frame[134:138, x : x + 16] = 245
        use, reasons = scheduler.inspect(frame, frame_index=index)
        if use:
            selected[index] = reasons
    assert 5 in selected
    assert "local_textness_change" in selected[5]
    payload = scheduler.payload(scanned_frames=len(selected))
    assert 5 in payload["detector_candidate_frames"]
    assert set(payload["single_frame_retention_candidate_frames"]).issubset(
        payload["hard_textness_frames"]
    )
    assert len(payload["single_frame_retention_candidate_frames"]) < len(
        payload["detector_candidate_frames"]
    )


def test_persistent_text_is_scheduled_by_completeness_cadence() -> None:
    scheduler = EventFrameScheduler(
        fps=30.0,
        frame_count=30,
        duration_ms=1_000,
        heartbeat_fps=0.2,
        completeness_sample_fps=6.0,
        max_detector_fps=6.5,
    )
    frame = np.full((288, 512, 3), 72, dtype=np.uint8)
    for x in range(42, 462, 30):
        frame[218:250, x : x + 9] = 245
        frame[232:237, x : x + 20] = 245
    selected: dict[int, tuple[str, ...]] = {}
    for index in range(30):
        use, reasons = scheduler.inspect(frame, frame_index=index)
        if use:
            selected[index] = reasons
    completeness = [
        index
        for index, reasons in selected.items()
        if "completeness_text_candidate" in reasons
    ]
    assert len(completeness) >= 4
    payload = scheduler.payload(scanned_frames=len(selected))
    assert payload["policy"]["proxy_long_edge"] == 512
    assert payload["completeness_candidate_frames"] == completeness
    assert payload["policy"]["detector_candidate_is_retention_authority"] is False
    assert payload["policy"]["single_frame_retention_requires_local_cjk"] is True
    assert not set(completeness).intersection(
        payload["single_frame_retention_candidate_frames"]
    )


def test_audio_windows_do_not_pay_duplicate_completeness_cadence() -> None:
    scheduler = EventFrameScheduler(
        fps=30.0,
        frame_count=30,
        duration_ms=1_000,
        audio_windows=[CandidateWindow(0, 999, ("AUDIO_GUIDED",), 1.0)],
        audio_sample_fps=4.0,
        heartbeat_fps=0.2,
        completeness_sample_fps=6.0,
    )
    frame = np.full((288, 512, 3), 72, dtype=np.uint8)
    for x in range(42, 462, 30):
        frame[218:250, x : x + 9] = 245
        frame[232:237, x : x + 20] = 245

    selected: dict[int, tuple[str, ...]] = {}
    for index in range(30):
        use, reasons = scheduler.inspect(frame, frame_index=index)
        if use:
            selected[index] = reasons

    assert any("audio_guided" in reasons for reasons in selected.values())
    assert not any(
        "completeness_text_candidate" in reasons
        for reasons in selected.values()
    )
    assert scheduler.payload(scanned_frames=len(selected))["policy"][
        "completeness_inside_audio_windows"
    ] is False


def test_ordinary_local_textness_change_respects_visual_cooldown() -> None:
    scheduler = EventFrameScheduler(
        fps=30.0,
        frame_count=60,
        duration_ms=2_000,
        heartbeat_fps=0.2,
        visual_trigger_cooldown_ms=900,
    )
    ordinary = scheduler.probe.inspect(np.zeros((8, 8, 3), dtype=np.uint8))
    ordinary = ordinary.__class__(
        triggered=True,
        reason="local_textness_change",
        scene_score=0.0,
        tile_edge_score=0.5,
        max_tile_edge_delta=0.5,
        median_tile_edge_delta=0.0,
        textness_delta=0.5,
        max_tile_textness_delta=0.5,
        hard_textness_boundary=False,
        absolute_textness_score=0.9,
        text_component_count=6,
        absolute_text_candidate=True,
        strong_absolute_text_candidate=True,
    )
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    with patch.object(scheduler.probe, "inspect", return_value=ordinary):
        first_use, first_reasons = scheduler.inspect(frame, frame_index=1)
        second_use, second_reasons = scheduler.inspect(frame, frame_index=2)

    assert first_use is True
    assert "local_textness_change" in first_reasons
    assert "local_textness_change" not in second_reasons
    assert scheduler.payload(scanned_frames=1)["visual_trigger_count"] == 1
