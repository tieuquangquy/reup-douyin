from src.media_pipeline.video_renderer.source_text_provenance import (
    classify_source_scene_components,
    is_editor_caption_track,
)


def _track(index: int, *, kind: str = "ui") -> dict:
    return {
        "text_id": f"t{index}",
        "kind": kind,
        "start_frame": 10 + index,
        "end_frame": 30 + index,
        "geometry": {"x": 0.15 + index * 0.03, "y": 0.1 + index * 0.08, "width": 0.08, "height": 0.04},
        "render_policy": {"context": {"dense_ui": True, "simultaneous_count": 10}},
    }


def test_dense_non_hardsub_plane_is_source_scene_but_hardsub_is_not() -> None:
    tracks = [_track(index) for index in range(8)]
    tracks.append(_track(20, kind="hardsub"))
    regions = classify_source_scene_components(tracks, frame_count=100)
    assert len(regions) == 1
    assert regions[0]["classification"] == "SOURCE_SCENE_TEXT"
    assert "t20" not in regions[0]["track_ids"]
    assert len(regions[0]["track_ids"]) == 8


def test_sparse_ui_is_not_auto_classified() -> None:
    assert classify_source_scene_components([_track(1), _track(2)], frame_count=100) == []


def test_sparse_labels_expand_from_dense_seed_but_editor_shapes_do_not() -> None:
    phone = _track(1)
    phone["start_frame"] = 40
    phone["end_frame"] = 45
    editor_generic = _track(2)
    editor_generic["roles"] = ["generic"]
    editor_hardsub = _track(3)
    editor_hardsub["roles"] = ["hardsub"]
    editor_hardsub["geometry"]["y"] = 0.9
    regions = classify_source_scene_components(
        [phone, editor_generic, editor_hardsub],
        frame_count=100,
        seed_regions=[
            {
                "region_id": "seed_phone",
                "classification": "SOURCE_SCENE_TEXT",
                "start_frame": 10,
                "end_frame": 30,
                "region_roi": {"x": 0.05, "y": 0.05, "width": 0.5, "height": 0.7},
            }
        ],
    )
    assert len(regions) == 1
    assert regions[0]["track_ids"] == ["t1"]


def test_micro_ui_with_legacy_hardsub_role_is_source_not_editor_caption() -> None:
    track = _track(1)
    track["roles"] = ["ui_chip", "hardsub"]
    track["geometry"].update({"x": 0.24, "y": 0.88, "width": 0.15, "height": 0.05})
    track["render_policy"]["context"].update(
        {"source_kind": "ui", "micro_ui": True, "dense_ui": False}
    )
    assert not is_editor_caption_track(track)


def test_legacy_generic_bottom_lane_phrase_is_editor_caption() -> None:
    track = _track(7)
    track["roles"] = ["generic"]
    track["text_vi"] = "Giữ da, lọc bỏ xương"
    track["geometry"].update(
        {"x": 0.079, "y": 0.818, "width": 0.211, "height": 0.046}
    )
    track["render_policy"]["context"].update(
        {
            "source_kind": "ui",
            "micro_ui": True,
            "dense_ui": False,
            "simultaneous_count": 1,
        }
    )
    assert is_editor_caption_track(track)


def test_legacy_generic_bottom_lane_phrase_without_micro_ui_is_editor_caption() -> None:
    track = _track(8)
    track["roles"] = ["generic"]
    track["text_vi"] = "Ăn kèm bí ngòi xào"
    track["geometry"].update(
        {"x": 0.08, "y": 0.82, "width": 0.23, "height": 0.05}
    )
    track["render_policy"]["context"].update(
        {
            "source_kind": "ui",
            "micro_ui": False,
            "dense_ui": False,
            "simultaneous_count": 1,
        }
    )
    assert is_editor_caption_track(track)
