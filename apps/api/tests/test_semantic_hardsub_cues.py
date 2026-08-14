from __future__ import annotations

import json
from pathlib import Path

from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    build_phase2_contract,
    build_phase2_handoff,
)
from src.media_pipeline.frame_sampling.semantic_hardsub_cues import (
    apply_semantic_hardsub_authority,
)


def _authority(*, status: str = "APPROVED") -> dict:
    return {
        "authority_ref": {
            "segment_authority_sha256": "segment-authority",
        },
        "segments": [
            {
                "transcript_segment_id": "transcript-1",
                "segment_index": 0,
                "start_ms": 0,
                "end_ms": 2_000,
                "text": "你好世界",
                "raw_payload": {
                    "tokens": ["你", "好", "世", "界"],
                    "timestamps": [
                        [0, 500],
                        [500, 1_000],
                        [1_000, 1_500],
                        [1_500, 2_000],
                    ],
                    "timestamps_are_absolute": True,
                },
                "translation": {
                    "translation_segment_id": "translation-1",
                    "text": "Xin chào thế giới",
                    "status": status,
                },
            }
        ],
    }


def _row(
    text_id: str,
    text: str,
    start_frame: int,
    end_frame: int,
    *,
    box: list[float] | None = None,
    role: str | None = None,
) -> dict:
    row = {
        "text_id": text_id,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "box_coords": box or [100.0, 800.0, 900.0, 900.0],
        "ocr_text": text,
        "visual_provenance": {"classification": "EDITOR_OVERLAY"},
    }
    if role:
        row["semantic_role"] = role
    return row


def test_transition_noise_attaches_to_neighbor_and_platform_ui_is_protected() -> None:
    result = apply_semantic_hardsub_authority(
        [
            _row("stable", "你好世界", 0, 19),
            _row("flash", "AL立TT", 20, 20),
            _row("source-ui", "1天前·山东", 30, 39, role="ui_chip"),
        ],
        dialogue_authority=_authority(),
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )

    rows = {str(row["text_id"]): row for row in result.timeline}
    stable = dict(rows["stable"]["semantic_hardsub"])
    flash = dict(rows["flash"]["semantic_hardsub"])
    assert flash["transition_noise"] is True
    assert flash["action"] == "ATTACHED_TRANSITION_GEOMETRY"
    assert flash["cue_id"] == stable["cue_id"]
    assert {row["text_id"] for row in result.protected_source_tracks} == {
        "source-ui"
    }
    protected = result.protected_source_tracks[0]
    assert protected["visual_provenance"]["classification"] == "SOURCE_INTRINSIC"


def test_near_duplicate_ocr_typo_uses_asr_text_and_one_cue() -> None:
    result = apply_semantic_hardsub_authority(
        [
            _row("epoch-a", "你好", 0, 9),
            _row("epoch-b", "你妤", 1, 9),
        ],
        dialogue_authority=_authority(),
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )

    semantic = [dict(row["semantic_hardsub"]) for row in result.timeline]
    assert {row["cue_id"] for row in semantic} == {semantic[0]["cue_id"]}
    assert {row["canonical_text_authority"] for row in semantic} == {"你好"}
    assert all(row["classification"] == "DIALOGUE_HARDSUB" for row in semantic)
    assert all(row["alignment"]["transcript_start_ms"] == 0 for row in semantic)
    assert all(row["alignment"]["transcript_end_ms"] == 2_000 for row in semantic)


def test_approved_translation_is_split_monotonically_without_loss() -> None:
    result = apply_semantic_hardsub_authority(
        [
            _row("cue-a", "你好", 0, 9),
            _row("cue-b", "世界", 10, 19),
        ],
        dialogue_authority=_authority(),
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )

    by_start = sorted(
        (dict(row["semantic_hardsub"]) for row in result.timeline),
        key=lambda row: int(row["start_ms"]),
    )
    assert len({row["cue_id"] for row in by_start}) == 2
    planned = [row["vi_text_authority"] for row in by_start]
    assert planned == ["Xin chào", "thế giới"]
    assert " ".join(planned) == "Xin chào thế giới"
    assert result.summary["ready"] is True


def test_short_translation_uses_one_display_epoch_and_cover_only_peers() -> None:
    authority = _authority()
    authority["segments"][0]["translation"]["text"] = "Được"
    result = apply_semantic_hardsub_authority(
        [
            _row("cue-a", "你好", 0, 9),
            _row("cue-b", "世界", 10, 19),
        ],
        dialogue_authority=authority,
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )

    semantic = [dict(row["semantic_hardsub"]) for row in result.timeline]
    assert [row.get("vi_text_authority") for row in semantic].count("Được") == 1
    assert sum(
        row.get("action") == "COVER_ONLY_DIALOGUE_EPOCH" for row in semantic
    ) == 1
    assert result.summary["ready"] is True


def test_unapproved_dialogue_blocks_handoff_and_never_enters_caption_ai(
    tmp_path: Path,
) -> None:
    phase1 = tmp_path / "master_timeline.json"
    phase1.write_text("[]", encoding="utf-8")
    result = apply_semantic_hardsub_authority(
        [_row("dialogue", "你好世界", 0, 19)],
        dialogue_authority=_authority(status="DRAFT"),
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )
    contract = build_phase2_contract(
        result.timeline,
        phase1_timeline_path=phase1,
        provider_mode="local",
        model_version="test",
        semantic_hardsub_summary=result.summary,
        fps=10.0,
        frame_width=1_080,
        frame_height=1_920,
    )
    phase2 = tmp_path / "phase2_ocr_timeline.json"
    phase2.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    handoff = build_phase2_handoff(contract, phase2_timeline_path=phase2)

    content = contract["content_objects"][0]
    assert content["localization"]["mode"] == "semantic_dialogue_pending"
    assert content["review_required"] is False
    assert handoff["status"] == "HANDOFF_BLOCKED"
    assert handoff["translate_items"] == []
    assert handoff["deterministic_items"] == []
    assert handoff["blocked_reasons"] == [
        "semantic_dialogue_translation_unapproved:ocr_content_001"
    ]


def test_missing_provenance_fails_closed_and_semantic_authority_changes_hash(
    tmp_path: Path,
) -> None:
    phase1 = tmp_path / "master_timeline.json"
    phase1.write_text("[]", encoding="utf-8")
    legacy = {
        "text_id": "legacy",
        "start_frame": 0,
        "end_frame": 3,
        "box_coords": [0, 0, 100, 40],
        "ocr_text": "标签",
    }
    legacy_contract = build_phase2_contract(
        [legacy],
        phase1_timeline_path=phase1,
        provider_mode="local",
        model_version="test",
    )
    assert legacy_contract["content_objects"][0][
        "provenance_classifications"
    ] == ["UNCERTAIN"]

    semantic_row = _row("label", "午餐", 0, 3)
    semantic_row["semantic_hardsub"] = {
        "schema_version": "semantic_hardsub_cues_v1",
        "recipe_version": "test",
        "cue_id": "cue-label",
        "classification": "EDITOR_LABEL",
        "canonical_text_authority": "午餐",
        "action": "CANDIDATE",
    }
    first = build_phase2_contract(
        [semantic_row],
        phase1_timeline_path=phase1,
        provider_mode="local",
        model_version="test",
        semantic_hardsub_summary={"authority_sha256": "authority-a"},
    )
    second = build_phase2_contract(
        [semantic_row],
        phase1_timeline_path=phase1,
        provider_mode="local",
        model_version="test",
        semantic_hardsub_summary={"authority_sha256": "authority-b"},
    )
    assert first["content_objects"][0]["review_input_sha256"] != second[
        "content_objects"
    ][0]["review_input_sha256"]
