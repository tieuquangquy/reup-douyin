from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.services.residual_remediation_authority import (
    ResidualRemediationAuthorityError,
    build_active_remediation_pointer,
    resolve_active_residual_remediation,
)


def test_legacy_remediation_is_default_without_pointer() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = root / "phase2_residual_remediation.json"
        legacy.write_text("{}", encoding="utf-8")

        assert resolve_active_residual_remediation(root) == legacy


def test_hash_bound_pointer_selects_versioned_remediation() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        versioned = root / "phase2_residual_remediation_abc.json"
        versioned.write_text("{}", encoding="utf-8")
        pointer = build_active_remediation_pointer(
            root=root,
            remediation_path=versioned,
            remediation_sha256="a" * 64,
        )
        (root / "phase2_residual_remediation_active.json").write_text(
            json.dumps(pointer), encoding="utf-8"
        )

        assert resolve_active_residual_remediation(root) == versioned


def test_pointer_fails_closed_when_versioned_file_drifts() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        versioned = root / "phase2_residual_remediation_abc.json"
        versioned.write_text("approved", encoding="utf-8")
        pointer = build_active_remediation_pointer(
            root=root,
            remediation_path=versioned,
            remediation_sha256="a" * 64,
        )
        (root / "phase2_residual_remediation_active.json").write_text(
            json.dumps(pointer), encoding="utf-8"
        )
        versioned.write_text("drifted", encoding="utf-8")

        with pytest.raises(
            ResidualRemediationAuthorityError,
            match="stale",
        ):
            resolve_active_residual_remediation(root)
