"""TTS Ops runtime snapshot helpers (last install + last probe/catalog)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_runtime() -> dict[str, Any]:
    return {"last_install": None, "last_probe": None}


def normalize_runtime(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_runtime()
    last_install = raw.get("last_install")
    last_probe = raw.get("last_probe")
    return {
        "last_install": dict(last_install) if isinstance(last_install, dict) else None,
        "last_probe": dict(last_probe) if isinstance(last_probe, dict) else None,
    }


def build_last_install(
    *,
    ok: bool,
    command: str,
    package: str,
    detail: str,
    already_satisfied: bool = False,
    status: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "at": utc_now_iso(),
        "ok": bool(ok),
        "command": (command or "").strip(),
        "package": (package or "").strip(),
        "detail": (detail or "").strip()[:500],
        "already_satisfied": bool(already_satisfied),
    }
    cleaned_status = (status or "").strip()
    if cleaned_status:
        row["status"] = cleaned_status
    return row


def build_last_probe(
    *,
    ok: bool,
    provider: str,
    detail: str,
    catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "at": utc_now_iso(),
        "ok": bool(ok),
        "provider": (provider or "").strip(),
        "detail": (detail or "").strip()[:800],
        "catalog": dict(catalog) if isinstance(catalog, dict) else None,
    }


def merge_runtime(
    existing: Any,
    *,
    last_install: dict[str, Any] | None = None,
    last_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = normalize_runtime(existing)
    if last_install is not None:
        base["last_install"] = last_install
    if last_probe is not None:
        base["last_probe"] = last_probe
    return base


def detect_already_satisfied(log_tail: str, detail: str = "") -> bool:
    text = f"{detail}\n{log_tail}".lower()
    return "already satisfied" in text or "requirement already satisfied" in text
