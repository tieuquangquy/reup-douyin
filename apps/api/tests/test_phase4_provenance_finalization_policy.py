from scripts.materialize_phase4_provenance_finalization import (
    EDITOR_CAPTION_COVER_OVERRIDES,
    EDITOR_CAPTION_SUPPLEMENTAL_COVERS,
    POLICY_VERSION,
)


def test_v22_65_editor_caption_covers_close_transition_gaps() -> None:
    override = EDITOR_CAPTION_COVER_OVERRIDES["sub_20"]
    roi = override["roi"]

    assert POLICY_VERSION == "phase4_source_text_provenance_finalization_v14"
    assert float(roi["x"]) + float(roi["width"]) == 0.36
    assert override["mask_mode"] == "editor_caption_stylized_components"

    supplement = EDITOR_CAPTION_SUPPLEMENTAL_COVERS[
        "sub_20__right_glyph_cover"
    ]
    geometry = supplement["geometry"]
    assert supplement["parent_text_id"] == "sub_20"
    assert float(geometry["x"]) <= 0.42
    assert float(geometry["x"]) + float(geometry["width"]) >= 0.45
    assert float(geometry["width"]) * float(geometry["height"]) <= 0.003
    assert supplement["mask_mode"] == "full_roi_plate"
    assert supplement["strategy"] == "spatial_telea_r9"

    bottom_override = EDITOR_CAPTION_COVER_OVERRIDES["sub_28"]
    bottom_roi = bottom_override["roi"]
    assert float(bottom_roi["x"]) <= 0.16
    assert float(bottom_roi["x"]) + float(bottom_roi["width"]) >= 0.80
    assert bottom_override["mask_mode"] == "editor_caption_stylized_components"

    transition = EDITOR_CAPTION_SUPPLEMENTAL_COVERS[
        "sub_28__transition_cover"
    ]
    assert transition["parent_text_id"] == "sub_28"
    assert transition["start_frame"] == 185
    assert transition["end_frame"] == 187
    assert transition["mask_mode"] == "editor_caption_stylized_components"

    left_cover = EDITOR_CAPTION_SUPPLEMENTAL_COVERS["sub_28__left_glyph_cover"]
    assert left_cover["start_frame"] == 188
    assert left_cover["end_frame"] == 439
    assert left_cover["mask_mode"] == "full_roi_plate"
    assert left_cover["strategy"] == "spatial_telea_r9"
