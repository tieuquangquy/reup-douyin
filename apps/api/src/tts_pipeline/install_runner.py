"""Allowlisted Local/SDK package install for Ops TTS (no arbitrary shell)."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_FORBIDDEN_CHARS = re.compile(r"[;&|`$<>\n\r]|\\|\.\.")
_PIP_INSTALL_RE = re.compile(
    r"^pip\s+install\s+"
    r"(?P<spec>"
    r"(?:git\+https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]+)"
    r"|(?:[A-Za-z0-9][A-Za-z0-9._\-]*(?:\[[A-Za-z0-9,_\-]+\])?(?:==[A-Za-z0-9._\-]+)?)"
    r")$"
)
_PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._\-]*(?:\[[A-Za-z0-9,_\-]+\])?(?:==[A-Za-z0-9._\-]+)?$"
)
_REPO_URL_RE = re.compile(
    r"^https://(github\.com|gitlab\.com)/[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+(?:\.git)?(?:@[A-Za-z0-9._/\-]+)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TtsInstallPlan:
    display_command: str
    argv: list[str]


@dataclass(frozen=True)
class TtsInstallResult:
    ok: bool
    detail: str
    command: str
    log_tail: str


class TtsInstallError(ValueError):
    """Invalid or disallowed install request."""


def build_tts_install_plan(
    *,
    install_command: str | None = None,
    package: str | None = None,
    repo_url: str | None = None,
) -> TtsInstallPlan:
    command = (install_command or "").strip()
    pkg = (package or "").strip()
    repo = (repo_url or "").strip()

    if command:
        return _plan_from_command(command)
    if pkg:
        if not _PACKAGE_RE.match(pkg):
            raise TtsInstallError("invalid_package")
        return _plan_from_command(f"pip install {pkg}")
    if repo:
        if not _REPO_URL_RE.match(repo):
            raise TtsInstallError("invalid_repo_url")
        git_spec = repo if repo.startswith("git+") else f"git+{repo}"
        return _plan_from_command(f"pip install {git_spec}")
    raise TtsInstallError("missing_install_source")


def _plan_from_command(command: str) -> TtsInstallPlan:
    cleaned = " ".join(command.strip().split())
    if _FORBIDDEN_CHARS.search(cleaned):
        raise TtsInstallError("disallowed_characters")
    match = _PIP_INSTALL_RE.match(cleaned)
    if not match:
        raise TtsInstallError(
            "install_command must look like: pip install <package> "
            "or pip install git+https://github.com/org/repo.git"
        )
    spec = match.group("spec")
    argv = [sys.executable, "-m", "pip", "install", spec]
    return TtsInstallPlan(display_command=f"pip install {spec}", argv=argv)


def run_tts_install(
    plan: TtsInstallPlan,
    *,
    timeout_seconds: float = 300.0,
    runner: Callable[[], subprocess.CompletedProcess[str]] | None = None,
) -> TtsInstallResult:
    timeout = max(30.0, min(float(timeout_seconds or 300.0), 900.0))
    logger.info("tts_install_started", extra={"command": plan.display_command})

    def _default_runner() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            plan.argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

    execute = runner or _default_runner
    try:
        completed = execute()
    except subprocess.TimeoutExpired:
        return TtsInstallResult(
            ok=False,
            detail=f"Install timed out after {timeout:.0f}s",
            command=plan.display_command,
            log_tail="",
        )
    except Exception as exc:  # noqa: BLE001 — surface to Ops UI
        return TtsInstallResult(
            ok=False,
            detail=f"Install failed to start: {exc}",
            command=plan.display_command,
            log_tail="",
        )

    combined = "\n".join(
        part for part in [(completed.stdout or "").strip(), (completed.stderr or "").strip()] if part
    )
    log_tail = combined[-4000:]
    if completed.returncode == 0:
        logger.info("tts_install_succeeded", extra={"command": plan.display_command})
        return TtsInstallResult(
            ok=True,
            detail="Package installed into the API/worker Python environment.",
            command=plan.display_command,
            log_tail=log_tail,
        )
    logger.warning(
        "tts_install_failed",
        extra={"command": plan.display_command, "returncode": completed.returncode},
    )
    return TtsInstallResult(
        ok=False,
        detail=f"pip exited with code {completed.returncode}",
        command=plan.display_command,
        log_tail=log_tail,
    )
