"""Allowlisted Local/SDK package install for Ops TTS (no arbitrary shell)."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

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

    # Prefer git+ repo over a stale PyPI command (e.g. edge-tts left in the form).
    if repo:
        if not _REPO_URL_RE.match(repo):
            raise TtsInstallError("invalid_repo_url")
        cmd_is_git = bool(re.match(r"^pip\s+install\s+git\+", command, re.IGNORECASE)) if command else False
        if not command or not cmd_is_git:
            git_spec = repo if repo.startswith("git+") else f"git+{repo}"
            return _plan_from_command(f"pip install {git_spec}")

    if command:
        return _plan_from_command(command)
    if pkg:
        if not _PACKAGE_RE.match(pkg):
            raise TtsInstallError("invalid_package")
        return _plan_from_command(f"pip install {pkg}")
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


def dist_name_from_install_plan(plan: TtsInstallPlan) -> str:
    """Best-effort distribution / folder name for ``pip show`` checks."""
    if not plan.argv:
        return ""
    spec = plan.argv[-1]
    if spec.startswith("git+"):
        leaf = spec.rstrip("/").rsplit("/", 1)[-1]
        leaf = re.sub(r"@[^@]+$", "", leaf)
        return leaf.removesuffix(".git")
    return re.split(r"[\[=]", spec, maxsplit=1)[0].strip()


def _pip_show_candidates(name: str) -> list[str]:
    raw = (name or "").strip()
    if not raw:
        return []
    variants = {
        raw,
        raw.replace("_", "-"),
        raw.replace("-", "_"),
        raw.lower(),
        raw.lower().replace("_", "-"),
        raw.lower().replace("-", "_"),
    }
    return [v for v in variants if v]


def is_tts_package_installed(
    plan: TtsInstallPlan,
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> bool:
    """Return True when ``pip show`` finds the planned package in this Python env."""
    name = dist_name_from_install_plan(plan)
    if not name:
        return False

    def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )

    execute = runner or _run
    for candidate in _pip_show_candidates(name):
        completed = execute([sys.executable, "-m", "pip", "show", candidate])
        if completed.returncode == 0 and (completed.stdout or "").strip():
            return True
    return False


def with_force_reinstall(plan: TtsInstallPlan) -> TtsInstallPlan:
    """Add ``--upgrade`` so git+/PyPI reinstall pulls a newer revision when possible."""
    argv = list(plan.argv)
    try:
        idx = argv.index("install")
    except ValueError:
        return plan
    if "--upgrade" in argv:
        return plan
    argv.insert(idx + 1, "--upgrade")
    display = plan.display_command.replace("pip install ", "pip install --upgrade ", 1)
    return TtsInstallPlan(display_command=display, argv=argv)


def run_tts_install(
    plan: TtsInstallPlan,
    *,
    timeout_seconds: float = 300.0,
    runner: Callable[[], subprocess.CompletedProcess[str] | SimpleNamespace] | None = None,
) -> TtsInstallResult:
    timeout = max(30.0, min(float(timeout_seconds or 300.0), 900.0))
    logger.info("tts_install_started", extra={"command": plan.display_command})

    def _default_runner() -> SimpleNamespace:
        # Avoid pipe deadlock when pip emits a large log (do not use capture_output).
        with tempfile.TemporaryDirectory(prefix="tts-pip-") as tmp:
            out_path = Path(tmp) / "stdout.txt"
            err_path = Path(tmp) / "stderr.txt"
            with out_path.open("w", encoding="utf-8", errors="replace") as out_f, err_path.open(
                "w", encoding="utf-8", errors="replace"
            ) as err_f:
                completed = subprocess.run(
                    plan.argv,
                    check=False,
                    stdout=out_f,
                    stderr=err_f,
                    text=True,
                    timeout=timeout,
                    shell=False,
                )
            stdout = out_path.read_text(encoding="utf-8", errors="replace")
            stderr = err_path.read_text(encoding="utf-8", errors="replace")
        return SimpleNamespace(returncode=completed.returncode, stdout=stdout, stderr=stderr)

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
