from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_profile_path_token(profile_path: str | Path) -> str:
    return str(Path(profile_path)).replace("/", "\\").lower()


def is_safe_playwright_profile_process(command_line: str, profile_path: str | Path) -> bool:
    """Only orphan Playwright/.douyin_profiles processes — never Google Chrome user profiles."""
    if not command_line:
        return False
    lowered = command_line.lower()
    token = normalize_profile_path_token(profile_path)
    if token not in lowered.replace("/", "\\"):
        return False
    if "ms-playwright" in lowered:
        return True
    if ".douyin_profiles" in lowered.replace("/", "\\"):
        return True
    return False


def list_orphaned_chromium_pids_for_profile(profile_path: str | Path, *, process_rows: list[tuple[int, str]]) -> list[int]:
    pids: list[int] = []
    for pid, command_line in process_rows:
        if is_safe_playwright_profile_process(command_line, profile_path):
            # Prefer root browser process only (no --type=).
            if "--type=" in (command_line or "").lower():
                continue
            pids.append(pid)
    return pids


def terminate_orphaned_chromium_for_profile(profile_path: str | Path) -> int:
    """Kill orphan Playwright Chromium holding our persistent profile (Windows local Phase 1)."""
    if os.name != "nt":
        return 0
    try:
        import subprocess

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        raw = (completed.stdout or "").strip()
        if not raw:
            return 0
        import json

        data = json.loads(raw)
        rows_raw = data if isinstance(data, list) else [data]
        rows: list[tuple[int, str]] = []
        for item in rows_raw:
            if not isinstance(item, dict):
                continue
            pid = item.get("ProcessId")
            cmd = item.get("CommandLine") or ""
            if isinstance(pid, int):
                rows.append((pid, str(cmd)))
        pids = list_orphaned_chromium_pids_for_profile(profile_path, process_rows=rows)
        killed = 0
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=10, check=False)
                killed += 1
                logger.warning(
                    "terminated_orphaned_playwright_profile_process",
                    extra={"pid": pid, "profile_path": str(profile_path)},
                )
            except Exception:
                logger.exception("terminate_orphaned_playwright_profile_process_failed", extra={"pid": pid})
        return killed
    except Exception:
        logger.exception("terminate_orphaned_chromium_for_profile_failed", extra={"profile_path": str(profile_path)})
        return 0


def should_retry_playwright_open_after_orphan_release(reason: str | None) -> bool:
    if not reason:
        return False
    return (
        reason.startswith("profile_locked_by_existing_process")
        or reason.startswith("first_page_closed_early")
        or reason.startswith("managed_runtime_reopen_failed")
        or reason.startswith("browser_context_lost")
    )
