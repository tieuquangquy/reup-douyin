from __future__ import annotations

from scripts.rebind_phase3_approvals_after_residual_remediation import (
    _collapse_merged_carry_rows,
)


def test_collapses_hash_bound_geometry_carry_row_into_matching_peer() -> None:
    carry = {
        "content_a": {
            "zh_approved": "下入西红柿",
            "vi_text_approved": "Cho cà chua vào",
        },
        "content_b": {
            "zh_approved": "下入西红柿",
            "vi_text_approved": "Cho cà chua vào",
        },
    }
    queue = {
        "content_a": {
            "zh_approved": "下入西红柿",
            "geometry_refs": ["sub_08", "sub_09"],
        }
    }
    remediation = {
        "approved_geometry_overrides": [
            {
                "geometry_override": {"target_text_id": "sub_09"},
                "localization": {"content_id": "content_b"},
            }
        ]
    }

    collapsed, audit = _collapse_merged_carry_rows(carry, queue, remediation)

    assert set(collapsed) == {"content_a"}
    assert audit == [
        {
            "missing_content_id": "content_b",
            "merged_into_content_id": "content_a",
        }
    ]


def test_does_not_collapse_without_exact_geometry_binding() -> None:
    carry = {
        "content_a": {"zh_approved": "甲", "vi_text_approved": "A"},
        "content_b": {"zh_approved": "甲", "vi_text_approved": "A"},
    }
    queue = {"content_a": {"zh_approved": "甲", "geometry_refs": ["sub_01"]}}

    collapsed, audit = _collapse_merged_carry_rows(carry, queue, {})

    assert collapsed == carry
    assert audit == []
