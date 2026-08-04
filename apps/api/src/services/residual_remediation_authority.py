"""Resolve versioned Phase-2 residual-remediation authority safely."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ACTIVE_POINTER_NAME = "phase2_residual_remediation_active.json"
LEGACY_REMEDIATION_NAME = "phase2_residual_remediation.json"


class ResidualRemediationAuthorityError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_active_remediation_pointer(
    *, root: Path, remediation_path: Path, remediation_sha256: str
) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved = remediation_path.resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ResidualRemediationAuthorityError(
            "Active remediation path is outside the artifact root"
        )
    file_sha = sha256_file(resolved)
    self_sha = str(remediation_sha256 or "")
    if len(self_sha) != 64:
        raise ResidualRemediationAuthorityError(
            "Active remediation self-hash is invalid"
        )
    pointer: dict[str, Any] = {
        "schema_version": "phase2_residual_remediation_active_v1",
        "status": "ACTIVE",
        "remediation_ref": {
            "path": resolved.relative_to(resolved_root).as_posix(),
            "sha256": file_sha,
            "remediation_sha256": self_sha,
        },
    }
    pointer["pointer_sha256"] = sha256_json(pointer)
    return pointer


def resolve_active_residual_remediation(root: str | Path) -> Path | None:
    resolved_root = Path(root).resolve()
    pointer_path = resolved_root / ACTIVE_POINTER_NAME
    if not pointer_path.is_file():
        legacy = resolved_root / LEGACY_REMEDIATION_NAME
        return legacy if legacy.is_file() else None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualRemediationAuthorityError(
            "Active remediation pointer is invalid"
        ) from exc
    if not isinstance(pointer, dict):
        raise ResidualRemediationAuthorityError(
            "Active remediation pointer must be an object"
        )
    unsigned = dict(pointer)
    claimed = str(unsigned.pop("pointer_sha256", "") or "")
    if (
        str(pointer.get("status") or "") != "ACTIVE"
        or len(claimed) != 64
        or claimed != sha256_json(unsigned)
    ):
        raise ResidualRemediationAuthorityError(
            "Active remediation pointer self-hash is invalid"
        )
    ref = dict(pointer.get("remediation_ref") or {})
    path = (resolved_root / str(ref.get("path") or "")).resolve()
    if (
        not path.is_relative_to(resolved_root)
        or not path.is_file()
        or sha256_file(path) != str(ref.get("sha256") or "")
        or len(str(ref.get("remediation_sha256") or "")) != 64
    ):
        raise ResidualRemediationAuthorityError(
            "Active remediation artifact is stale"
        )
    return path
