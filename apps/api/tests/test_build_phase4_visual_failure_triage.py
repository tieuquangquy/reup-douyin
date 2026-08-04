import json

from scripts import build_phase4_visual_failure_triage as triage_module
from scripts.build_phase4_visual_failure_triage import classify_failure
from scripts.build_phase4_visual_failure_triage import (
    _duplicate_output_residual_track_group,
)


def test_classifies_mask_quality_failure() -> None:
    result = classify_failure(
        "[P4-ADAPTIVE][FAIL] Adaptive frame blocked at index 111: "
        "Mask quality blocked for sub_07"
    )

    assert result == {
        "failure_class": "MASK_QUALITY_BLOCKED",
        "frame_index": 111,
        "text_id": "sub_07",
    }


def test_classifies_encoded_output_qa_failure() -> None:
    result = classify_failure(
        "[P4-ADAPTIVE][FAIL] Visual preview output QA failed "
        "(temporal_flicker,residual_cjk)"
    )

    assert result == {
        "failure_class": "ENCODED_OUTPUT_QA_FAILED",
        "failed_checks": ["temporal_flicker", "residual_cjk"],
    }


def test_classifies_reference_plate_alignment_failure() -> None:
    result = classify_failure(
        "[P4-ADAPTIVE][FAIL] Adaptive frame blocked at index 615: "
        "Reference plate alignment failed for p4out_01"
    )

    assert result == {
        "failure_class": "REFERENCE_PLATE_ALIGNMENT_BLOCKED",
        "frame_index": 615,
        "text_id": "p4out_01",
    }


def test_classify_failure_uses_latest_run_in_log() -> None:
    result = classify_failure(
        "[P4-ADAPTIVE][FAIL] Adaptive frame blocked at index 10: "
        "Mask quality blocked for sub_old\n"
        "[P4-ADAPTIVE][FAIL] Adaptive frame blocked at index 20: "
        "Mask quality blocked for sub_new"
    )

    assert result == {
        "failure_class": "MASK_QUALITY_BLOCKED",
        "frame_index": 20,
        "text_id": "sub_new",
    }


def test_classify_failure_prefers_later_output_qa_over_old_mask_block() -> None:
    result = classify_failure(
        "Adaptive frame blocked at index 20: Mask quality blocked for sub_old\n"
        "Visual preview output QA failed (residual_cjk)"
    )

    assert result == {
        "failure_class": "ENCODED_OUTPUT_QA_FAILED",
        "failed_checks": ["residual_cjk"],
    }


def test_direct_override_skips_stale_failures_from_other_cases(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "batch_regression_state.json").write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "local_current", "status": "FAILED"},
                    {"case_id": "local_stale", "status": "FAILED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    for case_id in ("local_current", "local_stale"):
        log = tmp_path / case_id / "logs" / "phase4_visual.log"
        log.parent.mkdir(parents=True)
        log.write_text(
            "Adaptive frame blocked at index 1: Mask quality blocked for sub_old",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        triage_module,
        "_build_mask_case",
        lambda _root, case_root, failure: {
            "case_id": case_root.name,
            **dict(failure),
            "recommendation": "TEST",
            "evidence": {},
        },
    )

    payload = triage_module.build_triage(
        tmp_path,
        output_stem="focused",
        mask_failure_overrides={
            "local_current": {"frame_index": 10, "text_id": "sub_new"}
        },
    )

    assert [row["case_id"] for row in payload["cases"]] == ["local_current"]


def test_duplicate_group_prefers_aligned_canonical_and_drops_all_others() -> None:
    group = _duplicate_output_residual_track_group(
        {
            "text_id": "p4out_target",
            "start_frame": 525,
            "end_frame": 614,
            "render_policy": {"context": {}},
        },
        [
            {
                "text_id": "p4out_aligned",
                "span": [525, 614],
                "geometry_aligned": True,
            },
            {
                "text_id": "p4out_duplicate",
                "span": [525, 614],
                "geometry_aligned": False,
            },
        ],
    )

    assert group is not None
    assert group["canonical_track_id"] == "p4out_aligned"
    assert group["drop_track_ids"] == ["p4out_duplicate", "p4out_target"]
