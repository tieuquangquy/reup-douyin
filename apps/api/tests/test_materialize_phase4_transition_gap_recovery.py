from __future__ import annotations

import unittest

from scripts.materialize_phase4_transition_gap_recovery import (
    build_merged_transition_track,
    build_gap_track,
    find_transition_gap_candidates,
    gap_sample_indices,
    recovered_transition_components,
)


def _track(text_id: str, start: int, end: int, *, text: str = "Lượng này đủ 2 bữa"):
    return {
        "text_id": text_id,
        "content_id": f"content_{text_id}",
        "start_frame": start,
        "end_frame": end,
        "start_ms": start * 33,
        "end_ms": (end + 1) * 33,
        "best_frame_index": start,
        "geometry": {"x": 0.05, "y": 0.81, "width": 0.27, "height": 0.05},
        "text_vi": text,
        "translation_status": "TRANSLATION_APPROVED",
        "render_policy": {
            "context": {"micro_ui": True},
            "cover": {
                "strategy": "adaptive_temporal_ink",
                "roi": {"x": 0.04, "y": 0.80, "width": 0.29, "height": 0.07},
            },
            "layout": {
                "mode": "anchored_text",
                "safe_area": {"x": 0.025, "y": 0.80, "width": 0.37, "height": 0.07},
            },
        },
    }


class TransitionGapRecoveryTests(unittest.TestCase):
    def test_finds_only_bounded_same_translation_gap(self) -> None:
        tracks = [
            _track("left", 314, 328),
            _track("right", 347, 351),
            _track("different", 355, 360, text="Cắt thành miếng lớn"),
        ]

        candidates = find_transition_gap_candidates(tracks, max_gap_frames=24)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["gap_start"], 329)
        self.assertEqual(candidates[0]["gap_end"], 346)

    def test_rejects_gap_when_geometry_does_not_overlap(self) -> None:
        left = _track("left", 10, 20)
        right = _track("right", 25, 30)
        right["geometry"] = {"x": 0.7, "y": 0.1, "width": 0.2, "height": 0.05}

        self.assertEqual(find_transition_gap_candidates([left, right]), [])

    def test_samples_start_middle_and_end(self) -> None:
        self.assertEqual(gap_sample_indices(329, 346), [329, 337, 346])

    def test_builds_hashable_supplemental_track_without_mutating_neighbor(self) -> None:
        previous = _track("left", 314, 328)
        following = _track("right", 347, 351)
        candidate = {
            "previous": previous,
            "following": following,
            "gap_start": 329,
            "gap_end": 346,
        }
        detections = [
            {"frame_index": 329, "text": "这些是两餐的量", "confidence": 0.99},
            {"frame_index": 337, "text": "这些是两餐的量", "confidence": 0.99},
            {"frame_index": 346, "text": "这些是两餐的量", "confidence": 0.99},
        ]

        recovered = build_gap_track(candidate, fps=30.0, detections=detections)

        self.assertEqual(recovered["start_frame"], 329)
        self.assertEqual(recovered["end_frame"], 346)
        self.assertEqual(recovered["text_vi"], following["text_vi"])
        self.assertEqual(following["start_frame"], 347)
        self.assertEqual(
            recovered["render_policy"]["context"]["transition_gap_recovery"],
            "phase4_transition_gap_recovery_v1",
        )

    def test_consolidates_touching_tracks_only_when_gap_member_is_present(self) -> None:
        previous = _track("left", 314, 328)
        gap = _track("gap", 329, 346)
        gap["render_policy"]["context"]["transition_gap_recovery"] = (
            "phase4_transition_gap_recovery_v1"
        )
        following = _track("right", 347, 351)

        components = recovered_transition_components([previous, gap, following])

        self.assertEqual(len(components), 1)
        self.assertEqual([row["text_id"] for row in components[0]], ["left", "gap", "right"])

    def test_merged_track_has_one_continuous_cache_identity(self) -> None:
        previous = _track("left", 314, 328)
        gap = _track("gap", 329, 346)
        gap["render_policy"]["context"]["transition_gap_recovery"] = (
            "phase4_transition_gap_recovery_v1"
        )
        following = _track("right", 347, 351)

        merged = build_merged_transition_track(
            [previous, gap, following], fps=30.0
        )

        self.assertEqual(merged["start_frame"], 314)
        self.assertEqual(merged["end_frame"], 351)
        self.assertTrue(merged["text_id"].startswith("p4gapmerge_"))
        self.assertEqual(
            merged["render_policy"]["context"]["transition_gap_merge"],
            "phase4_transition_gap_recovery_v1",
        )


if __name__ == "__main__":
    unittest.main()
