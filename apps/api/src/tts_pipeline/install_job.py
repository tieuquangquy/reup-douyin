"""In-memory async TTS package install jobs (Ops browser Install)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.tts_pipeline.install_runner import TtsInstallPlan, run_tts_install
from src.tts_pipeline.runtime_snapshot import (
    build_last_install,
    build_last_probe,
    detect_already_satisfied,
)

logger = logging.getLogger(__name__)

InstallStatus = str  # "running" | "succeeded" | "failed"


@dataclass
class TtsInstallJobSnapshot:
    workspace_id: str
    profile_id: str | None
    status: InstallStatus
    command: str
    package: str
    detail: str = ""
    log_tail: str = ""
    already_satisfied: bool = False
    probe_ok: bool | None = None
    probe_detail: str = ""
    provider: str = ""
    catalog: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None


@dataclass
class _JobRecord:
    snapshot: TtsInstallJobSnapshot
    lock: threading.Lock = field(default_factory=threading.Lock)


_REGISTRY_LOCK = threading.Lock()
_JOBS: dict[str, _JobRecord] = {}


def _key(workspace_id: UUID | str) -> str:
    return str(workspace_id)


def get_tts_install_job(workspace_id: UUID | str) -> TtsInstallJobSnapshot | None:
    with _REGISTRY_LOCK:
        record = _JOBS.get(_key(workspace_id))
        if record is None:
            return None
        with record.lock:
            snap = record.snapshot
            return TtsInstallJobSnapshot(
                workspace_id=snap.workspace_id,
                profile_id=snap.profile_id,
                status=snap.status,
                command=snap.command,
                package=snap.package,
                detail=snap.detail,
                log_tail=snap.log_tail,
                already_satisfied=snap.already_satisfied,
                probe_ok=snap.probe_ok,
                probe_detail=snap.probe_detail,
                provider=snap.provider,
                catalog=dict(snap.catalog) if isinstance(snap.catalog, dict) else None,
                runtime=dict(snap.runtime) if isinstance(snap.runtime, dict) else None,
            )


def start_tts_install_job(
    *,
    workspace_id: UUID,
    plan: TtsInstallPlan,
    package_name: str,
    provider: str | None,
    profile_id: str | None,
    timeout_seconds: float,
    force_reinstall: bool = False,
) -> TtsInstallJobSnapshot:
    """Start background pip install. Raises RuntimeError if a job is already running."""
    from src.tts_pipeline.install_runner import with_force_reinstall

    if force_reinstall:
        plan = with_force_reinstall(plan)
    ws_key = _key(workspace_id)
    package = (package_name or "").strip()
    if not package and plan.display_command.startswith("pip install "):
        package = plan.display_command.replace("pip install ", "", 1).strip()
        if package.startswith("git+"):
            package = package.rsplit("/", 1)[-1].removesuffix(".git")

    snapshot = TtsInstallJobSnapshot(
        workspace_id=ws_key,
        profile_id=(profile_id or "").strip() or None,
        status="running",
        command=plan.display_command,
        package=package,
        detail="Install running on the API host…",
        log_tail="",
    )

    with _REGISTRY_LOCK:
        existing = _JOBS.get(ws_key)
        if existing is not None:
            with existing.lock:
                if existing.snapshot.status == "running":
                    raise RuntimeError("A TTS package install is already running for this workspace")
        record = _JobRecord(snapshot=snapshot)
        _JOBS[ws_key] = record

    # Persist running marker before returning to the browser.
    try:
        from src.db.session import get_session_factory
        from src.services.workspace_settings_service import WorkspaceSettingsService

        with get_session_factory()() as db:
            service = WorkspaceSettingsService(db)
            runtime = service.patch_tts_ai_runtime(
                workspace_id,
                profile_id=snapshot.profile_id,
                last_install=build_last_install(
                    ok=False,
                    command=snapshot.command,
                    package=snapshot.package,
                    detail=snapshot.detail,
                    already_satisfied=False,
                    status="running",
                ),
            )
            with record.lock:
                record.snapshot.runtime = dict(runtime) if isinstance(runtime, dict) else runtime
    except Exception:  # noqa: BLE001
        logger.exception("tts_install_job_running_persist_failed", extra={"workspace_id": ws_key})

    thread = threading.Thread(
        target=_run_install_job,
        kwargs={
            "workspace_id": workspace_id,
            "plan": plan,
            "provider": (provider or "").strip() or None,
            "profile_id": snapshot.profile_id,
            "timeout_seconds": timeout_seconds,
            "package": package,
        },
        daemon=True,
        name=f"tts-install-{ws_key[:8]}",
    )
    thread.start()
    return get_tts_install_job(workspace_id) or snapshot


def _update_job(workspace_id: UUID | str, **fields: Any) -> None:
    with _REGISTRY_LOCK:
        record = _JOBS.get(_key(workspace_id))
        if record is None:
            return
    with record.lock:
        for key, value in fields.items():
            setattr(record.snapshot, key, value)


def _run_install_job(
    *,
    workspace_id: UUID,
    plan: TtsInstallPlan,
    provider: str | None,
    profile_id: str | None,
    timeout_seconds: float,
    package: str,
) -> None:
    from src.db.session import get_session_factory
    from src.services.workspace_settings_service import TtsAiConfig, WorkspaceSettingsService
    from src.tts_pipeline.provider_factory import probe_tts_ai_client

    ws_key = _key(workspace_id)
    try:
        result = run_tts_install(plan, timeout_seconds=timeout_seconds)
        already = detect_already_satisfied(result.log_tail, result.detail)
        probe_ok: bool | None = None
        probe_detail = ""
        provider_name = ""
        catalog: dict[str, Any] | None = None
        runtime: dict[str, Any] | None = None

        with get_session_factory()() as db:
            service = WorkspaceSettingsService(db)
            runtime = service.patch_tts_ai_runtime(
                workspace_id,
                profile_id=profile_id,
                last_install=build_last_install(
                    ok=result.ok,
                    command=result.command,
                    package=package,
                    detail=result.detail,
                    already_satisfied=already,
                    status="succeeded" if result.ok else "failed",
                ),
            )

            if result.ok:
                try:
                    if profile_id:
                        raw = (service._resolve_workspace(workspace_id).settings_json or {}).get("tts_ai")
                        _aid, profiles = service._normalize_tts_profiles(raw)
                        target = service._find_tts_profile(profiles, profile_id)
                        saved = service._parse_tts_ai(target or {})
                    else:
                        saved = service.get_tts_ai(workspace_id)
                    probe_provider = (provider or saved.provider or "auto").strip().lower()
                    probe_cfg = TtsAiConfig(
                        enabled=True,
                        provider=probe_provider,
                        voice_id=saved.voice_id,
                        speaking_rate=saved.speaking_rate,
                        language_code=saved.language_code,
                        model_id=saved.model_id,
                        api_key=saved.api_key,
                        base_url=saved.base_url,
                        timeout_seconds=saved.timeout_seconds,
                        fallback_provider=saved.fallback_provider,
                        fallback_voice_id=saved.fallback_voice_id,
                        local_backend=saved.local_backend,
                        device=saved.device,
                        cli_binary=saved.cli_binary,
                        options_json=dict(saved.options_json or {}),
                        runtime=saved.runtime,
                    )
                    probe = probe_tts_ai_client(probe_cfg)
                    probe_ok = probe.ok
                    probe_detail = probe.detail
                    provider_name = probe.provider
                    if probe.catalog:
                        catalog = dict(probe.catalog)
                    runtime = service.patch_tts_ai_runtime(
                        workspace_id,
                        profile_id=profile_id,
                        last_probe=build_last_probe(
                            ok=probe.ok,
                            provider=probe.provider,
                            detail=probe.detail,
                            catalog=probe.catalog,
                        ),
                    )
                except Exception as probe_exc:  # noqa: BLE001
                    logger.exception("tts_install_job_probe_failed", extra={"workspace_id": ws_key})
                    probe_ok = False
                    probe_detail = f"Install finished but probe failed: {probe_exc}"

        _update_job(
            workspace_id,
            status="succeeded" if result.ok else "failed",
            detail=result.detail,
            log_tail=result.log_tail,
            already_satisfied=already,
            probe_ok=probe_ok,
            probe_detail=probe_detail,
            provider=provider_name,
            catalog=catalog,
            runtime=dict(runtime) if isinstance(runtime, dict) else runtime,
            command=result.command,
            package=package,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("tts_install_job_failed", extra={"workspace_id": ws_key})
        detail = f"Install failed unexpectedly: {exc}"
        runtime = None
        try:
            with get_session_factory()() as db:
                service = WorkspaceSettingsService(db)
                runtime = service.patch_tts_ai_runtime(
                    workspace_id,
                    profile_id=profile_id,
                    last_install=build_last_install(
                        ok=False,
                        command=plan.display_command,
                        package=package,
                        detail=detail,
                        already_satisfied=False,
                        status="failed",
                    ),
                )
        except Exception:  # noqa: BLE001
            logger.exception("tts_install_job_fail_persist_failed", extra={"workspace_id": ws_key})
        _update_job(
            workspace_id,
            status="failed",
            detail=detail,
            log_tail="",
            already_satisfied=False,
            runtime=dict(runtime) if isinstance(runtime, dict) else runtime,
        )


def reset_tts_install_jobs_for_tests() -> None:
    """Test helper — clear in-memory registry."""
    with _REGISTRY_LOCK:
        _JOBS.clear()


def complete_tts_use_installed(
    *,
    workspace_id: UUID,
    plan: TtsInstallPlan,
    package_name: str,
    provider: str | None,
    profile_id: str | None,
) -> TtsInstallJobSnapshot:
    """Skip pip when the package is already present; persist + probe like a successful install."""
    from src.db.session import get_session_factory
    from src.services.workspace_settings_service import TtsAiConfig, WorkspaceSettingsService
    from src.tts_pipeline.catalog import discover_tts_catalog
    from src.tts_pipeline.install_runner import dist_name_from_install_plan
    from src.tts_pipeline.provider_factory import probe_tts_ai_client

    package = (package_name or "").strip() or dist_name_from_install_plan(plan)
    profile = (profile_id or "").strip() or None
    detail = (
        "Package already installed in the API/worker Python env. "
        "Skipped pip — use Reinstall / Upgrade to pull a newer revision."
    )
    probe_ok: bool | None = None
    probe_detail = ""
    provider_name = ""
    catalog: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None

    with get_session_factory()() as db:
        service = WorkspaceSettingsService(db)
        runtime = service.patch_tts_ai_runtime(
            workspace_id,
            profile_id=profile,
            last_install=build_last_install(
                ok=True,
                command=plan.display_command,
                package=package,
                detail=detail,
                already_satisfied=True,
                status="succeeded",
            ),
        )
        try:
            if profile:
                raw = (service._resolve_workspace(workspace_id).settings_json or {}).get("tts_ai")
                _aid, profiles = service._normalize_tts_profiles(raw)
                target = service._find_tts_profile(profiles, profile)
                saved = service._parse_tts_ai(target or {})
            else:
                saved = service.get_tts_ai(workspace_id)
            probe_provider = (provider or saved.provider or "auto").strip().lower()
            probe_cfg = TtsAiConfig(
                enabled=True,
                provider=probe_provider,
                voice_id=saved.voice_id,
                speaking_rate=saved.speaking_rate,
                language_code=saved.language_code,
                model_id=saved.model_id,
                api_key=saved.api_key,
                base_url=saved.base_url,
                timeout_seconds=saved.timeout_seconds,
                fallback_provider=saved.fallback_provider,
                fallback_voice_id=saved.fallback_voice_id,
                local_backend=saved.local_backend,
                device=saved.device,
                cli_binary=saved.cli_binary,
                options_json=dict(saved.options_json or {}),
                runtime=saved.runtime,
            )
            probe = probe_tts_ai_client(probe_cfg)
            probe_ok = probe.ok
            probe_detail = probe.detail
            provider_name = probe.provider
            if probe.catalog:
                catalog = dict(probe.catalog)
            else:
                curated = discover_tts_catalog(probe_provider, language_code=saved.language_code or "vi")
                catalog = curated.to_dict()
            runtime = service.patch_tts_ai_runtime(
                workspace_id,
                profile_id=profile,
                last_probe=build_last_probe(
                    ok=probe.ok,
                    provider=probe.provider,
                    detail=probe.detail,
                    catalog=catalog,
                ),
            )
        except Exception as probe_exc:  # noqa: BLE001
            logger.exception("tts_use_installed_probe_failed", extra={"workspace_id": str(workspace_id)})
            probe_ok = False
            probe_detail = f"Package is installed but probe failed: {probe_exc}"
            curated = discover_tts_catalog(
                (provider or "custom").strip().lower() or "custom",
                language_code="vi",
            )
            catalog = curated.to_dict()

    snapshot = TtsInstallJobSnapshot(
        workspace_id=str(workspace_id),
        profile_id=profile,
        status="succeeded",
        command=plan.display_command,
        package=package,
        detail=detail,
        log_tail="Requirement already satisfied (skipped pip).",
        already_satisfied=True,
        probe_ok=probe_ok,
        probe_detail=probe_detail,
        provider=provider_name,
        catalog=catalog,
        runtime=dict(runtime) if isinstance(runtime, dict) else runtime,
    )
    with _REGISTRY_LOCK:
        _JOBS[str(workspace_id)] = _JobRecord(snapshot=snapshot)
    return snapshot
