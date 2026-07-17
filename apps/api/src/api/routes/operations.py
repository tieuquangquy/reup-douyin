from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.audio_pipeline.provider_factory import probe_translation_ai_client
from src.audio_pipeline.translation_ai_models import list_translation_ai_models
from src.core.auth import get_current_workspace
from src.db.session import get_db_session
from src.schemas.operations import (
    OperationalMetricsResponse,
    TranslationAiModelsRequest,
    TranslationAiModelsResponse,
    TranslationAiResponse,
    TranslationAiTestRequest,
    TranslationAiTestResponse,
    TranslationAiUpdateRequest,
    TranslationPromptResponse,
    TranslationPromptUpdateRequest,
    TtsAiCatalog,
    TtsAiInstallRequest,
    TtsAiInstallResponse,
    TtsAiPreviewRequest,
    TtsAiPreviewResponse,
    TtsAiResponse,
    TtsAiRuntime,
    TtsAiTestRequest,
    TtsAiTestResponse,
    TtsAiUpdateRequest,
)
from src.services.operational_metrics import OperationalMetricsService
from src.services.workspace_settings_service import TranslationAiConfig, TtsAiConfig, WorkspaceSettingsService
from src.tts_pipeline.errors import TtsPipelineError
from src.tts_pipeline.install_runner import TtsInstallError, build_tts_install_plan, run_tts_install
from src.tts_pipeline.preview import PreviewTtsError, preview_tts_speech
from src.tts_pipeline.provider_factory import probe_tts_ai_client
from src.tts_pipeline.runtime_snapshot import (
    build_last_install,
    build_last_probe,
    detect_already_satisfied,
    normalize_runtime,
)
from src.core.settings import get_settings

router = APIRouter(prefix="/ops", tags=["operations"])


def get_operational_metrics_service(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> OperationalMetricsService:
    return OperationalMetricsService(db, workspace_id=workspace_id)


@router.get("/metrics", response_model=OperationalMetricsResponse)
def get_operational_metrics(
    service: OperationalMetricsService = Depends(get_operational_metrics_service),
) -> OperationalMetricsResponse:
    return service.get_metrics()


@router.get("/translation-prompt", response_model=TranslationPromptResponse)
def get_translation_prompt(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    prompt = WorkspaceSettingsService(db).get_translation_user_prompt(workspace_id) or ""
    return TranslationPromptResponse(
        prompt=prompt,
        source="workspace_db" if prompt else "empty",
    )


@router.put("/translation-prompt", response_model=TranslationPromptResponse)
def put_translation_prompt(
    body: TranslationPromptUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    try:
        saved = WorkspaceSettingsService(db).set_translation_user_prompt(workspace_id, body.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TranslationPromptResponse(
        prompt=saved,
        source="workspace_db" if saved else "empty",
        updated=True,
    )


def _translation_ai_response(public: dict, *, updated: bool = False) -> TranslationAiResponse:
    return TranslationAiResponse(
        enabled=bool(public.get("enabled")),
        provider=str(public.get("provider") or "auto"),
        model=str(public.get("model") or ""),
        api_key_set=bool(public.get("api_key_set")),
        api_key_masked=str(public.get("api_key_masked") or ""),
        base_url=str(public.get("base_url") or ""),
        timeout_seconds=float(public.get("timeout_seconds") or 90.0),
        fallback_provider=str(public.get("fallback_provider") or "none"),
        fallback_model=str(public.get("fallback_model") or ""),
        source=str(public.get("source") or "env"),
        updated=updated,
    )


@router.get("/translation-ai", response_model=TranslationAiResponse)
def get_translation_ai(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    public = WorkspaceSettingsService(db).get_translation_ai_public(workspace_id)
    return _translation_ai_response(public)


@router.put("/translation-ai", response_model=TranslationAiResponse)
def put_translation_ai(
    body: TranslationAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_translation_ai(
            workspace_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True)


@router.post("/translation-ai/test", response_model=TranslationAiTestResponse)
def test_translation_ai(
    body: TranslationAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiTestResponse:
    service = WorkspaceSettingsService(db)
    saved = service.get_translation_ai(workspace_id)
    draft = body.model_dump(exclude_none=True)
    if not draft and not body.clear_api_key:
        cfg = saved
    else:
        api_key = saved.api_key
        if body.clear_api_key:
            api_key = None
        elif body.api_key is not None:
            cleaned = body.api_key.strip()
            api_key = cleaned or None
        cfg = TranslationAiConfig(
            enabled=bool(body.enabled if body.enabled is not None else saved.enabled or True),
            provider=str(body.provider if body.provider is not None else saved.provider),
            model=str(body.model if body.model is not None else saved.model),
            api_key=api_key,
            base_url=str(body.base_url if body.base_url is not None else saved.base_url),
            timeout_seconds=float(
                body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds
            ),
            fallback_provider=str(
                body.fallback_provider if body.fallback_provider is not None else saved.fallback_provider
            ),
            fallback_model=str(body.fallback_model if body.fallback_model is not None else saved.fallback_model),
        )
    ok, provider_name, detail = probe_translation_ai_client(cfg)
    return TranslationAiTestResponse(ok=ok, provider=provider_name, detail=detail)


def _resolve_translation_ai_draft_key(
    *,
    saved: TranslationAiConfig,
    api_key: str | None,
    clear_api_key: bool,
) -> str | None:
    if clear_api_key:
        return None
    if api_key is not None:
        cleaned = api_key.strip()
        return cleaned or None
    return saved.api_key


@router.post("/translation-ai/models", response_model=TranslationAiModelsResponse)
def list_translation_ai_models_route(
    body: TranslationAiModelsRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiModelsResponse:
    service = WorkspaceSettingsService(db)
    saved = service.get_translation_ai(workspace_id)
    provider = str(body.provider or saved.provider or "auto").strip().lower()
    api_key = _resolve_translation_ai_draft_key(
        saved=saved,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
    )
    base_url = str(body.base_url if body.base_url is not None else saved.base_url or "")
    timeout = float(body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds or 30.0)
    ok, models, detail = list_translation_ai_models(
        provider=provider,
        api_key=api_key or "",
        base_url=base_url,
        timeout_seconds=min(timeout, 60.0),
    )
    return TranslationAiModelsResponse(ok=ok, provider=provider, models=models, detail=detail)


# --- Caption AI settings (Phase 2.5 hard-sub) — separate from Translation settings ---


@router.get("/caption-prompt", response_model=TranslationPromptResponse)
def get_caption_prompt(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    prompt = WorkspaceSettingsService(db).get_caption_prompt(workspace_id) or ""
    return TranslationPromptResponse(
        prompt=prompt,
        source="workspace_db" if prompt else "empty",
    )


@router.put("/caption-prompt", response_model=TranslationPromptResponse)
def put_caption_prompt(
    body: TranslationPromptUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    try:
        saved = WorkspaceSettingsService(db).set_caption_prompt(workspace_id, body.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TranslationPromptResponse(
        prompt=saved,
        source="workspace_db" if saved else "empty",
        updated=True,
    )


@router.get("/caption-ai", response_model=TranslationAiResponse)
def get_caption_ai(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    public = WorkspaceSettingsService(db).get_caption_ai_public(workspace_id)
    return _translation_ai_response(public)


@router.put("/caption-ai", response_model=TranslationAiResponse)
def put_caption_ai(
    body: TranslationAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_caption_ai(
            workspace_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True)


@router.post("/caption-ai/test", response_model=TranslationAiTestResponse)
def test_caption_ai(
    body: TranslationAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiTestResponse:
    service = WorkspaceSettingsService(db)
    saved = service.get_caption_ai(workspace_id)
    draft = body.model_dump(exclude_none=True)
    if not draft and not body.clear_api_key:
        cfg = saved
    else:
        api_key = saved.api_key
        if body.clear_api_key:
            api_key = None
        elif body.api_key is not None:
            cleaned = body.api_key.strip()
            api_key = cleaned or None
        cfg = TranslationAiConfig(
            enabled=bool(body.enabled if body.enabled is not None else saved.enabled or True),
            provider=str(body.provider if body.provider is not None else saved.provider),
            model=str(body.model if body.model is not None else saved.model),
            api_key=api_key,
            base_url=str(body.base_url if body.base_url is not None else saved.base_url),
            timeout_seconds=float(
                body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds
            ),
            fallback_provider=str(
                body.fallback_provider if body.fallback_provider is not None else saved.fallback_provider
            ),
            fallback_model=str(body.fallback_model if body.fallback_model is not None else saved.fallback_model),
        )
    ok, provider_name, detail = probe_translation_ai_client(cfg)
    return TranslationAiTestResponse(ok=ok, provider=provider_name, detail=detail)


@router.post("/caption-ai/models", response_model=TranslationAiModelsResponse)
def list_caption_ai_models_route(
    body: TranslationAiModelsRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiModelsResponse:
    service = WorkspaceSettingsService(db)
    saved = service.get_caption_ai(workspace_id)
    provider = str(body.provider or saved.provider or "auto").strip().lower()
    api_key = _resolve_translation_ai_draft_key(
        saved=saved,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
    )
    base_url = str(body.base_url if body.base_url is not None else saved.base_url or "")
    timeout = float(body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds or 30.0)
    ok, models, detail = list_translation_ai_models(
        provider=provider,
        api_key=api_key or "",
        base_url=base_url,
        timeout_seconds=min(timeout, 60.0),
    )
    return TranslationAiModelsResponse(ok=ok, provider=provider, models=models, detail=detail)


def _tts_ai_response(public: dict, *, updated: bool = False) -> TtsAiResponse:
    runtime_raw = public.get("runtime") or {}
    runtime = TtsAiRuntime.model_validate(normalize_runtime(runtime_raw))
    return TtsAiResponse(
        enabled=bool(public.get("enabled")),
        provider=str(public.get("provider") or "auto"),
        voice_id=str(public.get("voice_id") or ""),
        speaking_rate=float(public.get("speaking_rate") or 1.0),
        language_code=str(public.get("language_code") or "vi"),
        model_id=str(public.get("model_id") or ""),
        api_key_set=bool(public.get("api_key_set")),
        api_key_masked=str(public.get("api_key_masked") or ""),
        base_url=str(public.get("base_url") or ""),
        timeout_seconds=float(public.get("timeout_seconds") or 120.0),
        fallback_provider=str(public.get("fallback_provider") or "none"),
        fallback_voice_id=str(public.get("fallback_voice_id") or ""),
        local_backend=str(public.get("local_backend") or "auto"),
        device=str(public.get("device") or "auto"),
        cli_binary=str(public.get("cli_binary") or ""),
        options_json=dict(public.get("options_json") or {}),
        runtime=runtime,
        live_import_ok=public.get("live_import_ok"),
        source=str(public.get("source") or "env"),
        updated=updated,
    )


@router.get("/tts-ai", response_model=TtsAiResponse)
def get_tts_ai(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    public = WorkspaceSettingsService(db).get_tts_ai_public(workspace_id)
    return _tts_ai_response(public)


@router.put("/tts-ai", response_model=TtsAiResponse)
def put_tts_ai(
    body: TtsAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_tts_ai(
            workspace_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public, updated=True)


@router.post("/tts-ai/test", response_model=TtsAiTestResponse)
def test_tts_ai(
    body: TtsAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiTestResponse:
    service = WorkspaceSettingsService(db)
    saved = service.get_tts_ai(workspace_id)
    draft = body.model_dump(exclude_none=True)
    if not draft and not body.clear_api_key:
        cfg = saved
    else:
        api_key = saved.api_key
        if body.clear_api_key:
            api_key = None
        elif body.api_key is not None:
            cleaned = body.api_key.strip()
            api_key = cleaned or None
        cfg = TtsAiConfig(
            enabled=bool(body.enabled if body.enabled is not None else saved.enabled or True),
            provider=str(body.provider if body.provider is not None else saved.provider),
            voice_id=str(body.voice_id if body.voice_id is not None else saved.voice_id),
            speaking_rate=float(
                body.speaking_rate if body.speaking_rate is not None else saved.speaking_rate
            ),
            language_code=str(
                body.language_code if body.language_code is not None else saved.language_code
            ),
            model_id=str(body.model_id if body.model_id is not None else saved.model_id),
            api_key=api_key,
            base_url=str(body.base_url if body.base_url is not None else saved.base_url),
            timeout_seconds=float(
                body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds
            ),
            fallback_provider=str(
                body.fallback_provider if body.fallback_provider is not None else saved.fallback_provider
            ),
            fallback_voice_id=str(
                body.fallback_voice_id if body.fallback_voice_id is not None else saved.fallback_voice_id
            ),
            local_backend=str(
                body.local_backend if body.local_backend is not None else saved.local_backend
            ),
            device=str(body.device if body.device is not None else saved.device),
            cli_binary=str(body.cli_binary if body.cli_binary is not None else saved.cli_binary),
            options_json=dict(
                body.options_json if body.options_json is not None else (saved.options_json or {})
            ),
        )
    result = probe_tts_ai_client(cfg)
    catalog = None
    if result.catalog:
        catalog = TtsAiCatalog.model_validate(result.catalog)
    runtime = service.patch_tts_ai_runtime(
        workspace_id,
        last_probe=build_last_probe(
            ok=result.ok,
            provider=result.provider,
            detail=result.detail,
            catalog=result.catalog,
        ),
    )
    return TtsAiTestResponse(
        ok=result.ok,
        provider=result.provider,
        detail=result.detail,
        catalog=catalog,
        runtime=TtsAiRuntime.model_validate(runtime),
    )


@router.post("/tts-ai/install", response_model=TtsAiInstallResponse)
def install_tts_ai_package(
    body: TtsAiInstallRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiInstallResponse:
    settings = get_settings()
    if not bool(getattr(settings, "audio_tts_allow_install", True)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TTS package install is disabled (AUDIO_TTS_ALLOW_INSTALL=false)",
        )
    try:
        plan = build_tts_install_plan(
            install_command=body.install_command,
            package=body.package,
            repo_url=body.repo_url,
        )
    except TtsInstallError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    result = run_tts_install(plan, timeout_seconds=body.timeout_seconds)
    already = detect_already_satisfied(result.log_tail, result.detail)
    package_name = (body.package or "").strip()
    if not package_name and result.command.startswith("pip install "):
        package_name = result.command.replace("pip install ", "", 1).strip()

    service = WorkspaceSettingsService(db)
    runtime = service.patch_tts_ai_runtime(
        workspace_id,
        last_install=build_last_install(
            ok=result.ok,
            command=result.command,
            package=package_name,
            detail=result.detail,
            already_satisfied=already,
        ),
    )

    probe_ok: bool | None = None
    probe_detail = ""
    provider_name = ""
    catalog = None
    if result.ok:
        saved = service.get_tts_ai(workspace_id)
        probe_provider = (body.provider or saved.provider or "auto").strip().lower()
        # Probe using saved connection fields but the provider we just installed for.
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
            catalog = TtsAiCatalog.model_validate(probe.catalog)
        runtime = service.patch_tts_ai_runtime(
            workspace_id,
            last_probe=build_last_probe(
                ok=probe.ok,
                provider=probe.provider,
                detail=probe.detail,
                catalog=probe.catalog,
            ),
        )

    return TtsAiInstallResponse(
        ok=result.ok,
        detail=result.detail,
        command=result.command,
        log_tail=result.log_tail,
        already_satisfied=already,
        probe_ok=probe_ok,
        probe_detail=probe_detail,
        provider=provider_name,
        catalog=catalog,
        runtime=TtsAiRuntime.model_validate(runtime),
    )


@router.post("/tts-ai/preview", response_model=TtsAiPreviewResponse)
def preview_tts_ai_speech(
    body: TtsAiPreviewRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiPreviewResponse:
    """One-shot synthesize of short sample text using the Ops draft connection."""
    service = WorkspaceSettingsService(db)
    saved = service.get_tts_ai(workspace_id)
    api_key = saved.api_key
    if body.clear_api_key:
        api_key = None
    elif body.api_key is not None:
        cleaned = body.api_key.strip()
        api_key = cleaned or None
    cfg = TtsAiConfig(
        enabled=True,
        provider=str(body.provider if body.provider is not None else saved.provider),
        voice_id=str(body.voice_id if body.voice_id is not None else saved.voice_id),
        speaking_rate=float(
            body.speaking_rate if body.speaking_rate is not None else saved.speaking_rate
        ),
        language_code=str(
            body.language_code if body.language_code is not None else saved.language_code
        ),
        model_id=str(body.model_id if body.model_id is not None else saved.model_id),
        api_key=api_key,
        base_url=str(body.base_url if body.base_url is not None else saved.base_url),
        timeout_seconds=float(
            body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds
        ),
        fallback_provider=str(
            body.fallback_provider if body.fallback_provider is not None else saved.fallback_provider
        ),
        fallback_voice_id=str(
            body.fallback_voice_id if body.fallback_voice_id is not None else saved.fallback_voice_id
        ),
        local_backend=str(
            body.local_backend if body.local_backend is not None else saved.local_backend
        ),
        device=str(body.device if body.device is not None else saved.device),
        cli_binary=str(body.cli_binary if body.cli_binary is not None else saved.cli_binary),
        options_json=dict(
            body.options_json if body.options_json is not None else (saved.options_json or {})
        ),
        runtime=saved.runtime,
    )
    try:
        result = preview_tts_speech(
            workspace_tts=cfg,
            text=body.text,
            max_chars=body.max_chars,
        )
    except PreviewTtsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TtsPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    return TtsAiPreviewResponse(**result)

