from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.audio_pipeline.provider_factory import probe_translation_ai_client
from src.audio_pipeline.translation_ai_models import list_models_timeout_seconds, list_translation_ai_models
from src.core.auth import get_current_workspace
from src.db.session import get_db_session
from src.schemas.operations import (
    OperationalMetricsResponse,
    ProfileReorderRequest,
    PromptProfileCreateRequest,
    PromptProfilePatchRequest,
    PromptProfileSummary,
    PromptProfileUpdateRequest,
    TranslationAiModelsRequest,
    TranslationAiModelsResponse,
    TranslationAiProfileCreateRequest,
    TranslationAiProfilePatchRequest,
    TranslationAiProfileSummary,
    TranslationAiResponse,
    TranslationAiTestRequest,
    TranslationAiTestResponse,
    TranslationAiUpdateRequest,
    TranslationPromptResponse,
    TranslationPromptUpdateRequest,
    TtsAiCatalog,
    TtsAiEngineCatalogResponse,
    TtsAiEngineInstallJobResponse,
    TtsAiEngineInstallRequest,
    TtsAiInstallRequest,
    TtsAiInstallResponse,
    TtsAiPreviewRequest,
    TtsAiPreviewResponse,
    TtsAiProfileCreateRequest,
    TtsAiProfilePatchRequest,
    TtsAiProfileSummary,
    TtsAiResponse,
    TtsAiRuntime,
    TtsAiTestRequest,
    TtsAiTestResponse,
    TtsAiUpdateRequest,
)
from src.services.operational_metrics import OperationalMetricsService
from src.services.workspace_settings_service import TranslationAiConfig, TtsAiConfig, WorkspaceSettingsService
from src.tts_pipeline.install_job import (
    complete_tts_use_installed,
    get_tts_install_job,
    start_tts_install_job,
)
from src.tts_pipeline.install_runner import (
    TtsInstallError,
    build_tts_install_plan,
    is_tts_package_installed,
)
from src.tts_pipeline.omnivoice_engine_catalog import (
    discover_omnivoice_engines,
    get_omnivoice_engine_install,
)
from src.tts_pipeline.omnivoice_engine_install_job import (
    get_engine_install_status,
    is_managed_engine_installed,
    start_engine_install,
)
from src.tts_pipeline.preview_job import (
    cancel_tts_preview_job,
    get_tts_preview_job,
    start_tts_preview_job,
)
from src.tts_pipeline.provider_factory import probe_tts_ai_client
from src.tts_pipeline.runtime_snapshot import (
    build_last_probe,
    normalize_runtime,
)
from src.core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["operations"])


def _tts_install_response_from_job(job) -> TtsAiInstallResponse:
    catalog = None
    if job.catalog:
        try:
            catalog = TtsAiCatalog.model_validate(job.catalog)
        except Exception:  # noqa: BLE001
            catalog = None
    runtime = None
    if job.runtime:
        try:
            runtime = TtsAiRuntime.model_validate(job.runtime)
        except Exception:  # noqa: BLE001
            runtime = TtsAiRuntime()
    status = job.status
    return TtsAiInstallResponse(
        ok=status == "succeeded",
        status=status,
        detail=job.detail,
        command=job.command,
        log_tail=job.log_tail,
        already_satisfied=job.already_satisfied,
        probe_ok=job.probe_ok,
        probe_detail=job.probe_detail,
        provider=job.provider,
        catalog=catalog,
        runtime=runtime,
    )


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


def _prompt_response(
    public: dict, *, updated: bool = False, focus_profile_id: str | None = None
) -> TranslationPromptResponse:
    profiles_raw = public.get("profiles") or []
    profiles = [PromptProfileSummary.model_validate(item) for item in profiles_raw]
    focus = focus_profile_id if focus_profile_id is not None else public.get("focus_profile_id")
    return TranslationPromptResponse(
        prompt=str(public.get("prompt") or ""),
        source=str(public.get("source") or "empty"),
        updated=updated,
        active_profile_id=str(public.get("active_profile_id") or ""),
        active_profile_name=str(public.get("active_profile_name") or "Default"),
        profiles=profiles,
        focus_profile_id=str(focus) if focus else None,
    )


def _prompt_value_error_code(detail: str) -> int:
    return status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST


@router.get("/translation-prompt", response_model=TranslationPromptResponse)
def get_translation_prompt(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    public = WorkspaceSettingsService(db).get_translation_prompt_public(workspace_id)
    return _prompt_response(public)


@router.put("/translation-prompt", response_model=TranslationPromptResponse)
def put_translation_prompt(
    body: TranslationPromptUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.set_translation_user_prompt(workspace_id, body.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_translation_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


@router.post("/translation-prompt/profiles", response_model=TranslationPromptResponse)
def create_translation_prompt_profile(
    body: PromptProfileCreateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        created = service.create_translation_prompt_profile(workspace_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_translation_prompt_public(workspace_id)
    return _prompt_response(public, updated=True, focus_profile_id=str(created.get("id") or ""))


@router.put("/translation-prompt/profiles/reorder", response_model=TranslationPromptResponse)
def reorder_translation_prompt_profiles(
    body: ProfileReorderRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.reorder_translation_prompt_profiles(workspace_id, body.profile_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _prompt_response(public, updated=True)


@router.get("/translation-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def get_translation_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.get_translation_prompt_profile_public(workspace_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _prompt_response(public)


@router.put("/translation-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def put_translation_prompt_profile(
    profile_id: str,
    body: PromptProfileUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.set_translation_prompt_profile(workspace_id, profile_id, prompt=body.prompt)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_translation_prompt_profile_public(workspace_id, profile_id)
    return _prompt_response(public, updated=True, focus_profile_id=profile_id)


@router.patch("/translation-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def patch_translation_prompt_profile(
    profile_id: str,
    body: PromptProfilePatchRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        if body.name is None:
            raise ValueError("empty_patch")
        service.rename_translation_prompt_profile(workspace_id, profile_id, name=body.name)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_translation_prompt_profile_public(workspace_id, profile_id)
    return _prompt_response(public, updated=True, focus_profile_id=profile_id)


@router.post(
    "/translation-prompt/profiles/{profile_id}/activate",
    response_model=TranslationPromptResponse,
)
def activate_translation_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.activate_translation_prompt_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_translation_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


@router.delete(
    "/translation-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse
)
def delete_translation_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.delete_translation_prompt_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_translation_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


def _translation_ai_response(
    public: dict, *, updated: bool = False, focus_profile_id: str | None = None
) -> TranslationAiResponse:
    profiles_raw = public.get("profiles") or []
    profiles = [TranslationAiProfileSummary.model_validate(item) for item in profiles_raw]
    focus = focus_profile_id if focus_profile_id is not None else public.get("focus_profile_id")
    return TranslationAiResponse(
        enabled=bool(public.get("enabled")),
        provider=str(public.get("provider") or "auto"),
        model=str(public.get("model") or ""),
        api_key_set=bool(public.get("api_key_set")),
        api_key_masked=str(public.get("api_key_masked") or ""),
        api_key=str(public.get("api_key") or ""),
        base_url=str(public.get("base_url") or ""),
        region=str(public.get("region") or "global"),
        timeout_seconds=float(public.get("timeout_seconds") or 90.0),
        fallback_provider=str(public.get("fallback_provider") or "none"),
        fallback_model=str(public.get("fallback_model") or ""),
        source=str(public.get("source") or "env"),
        updated=updated,
        active_profile_id=str(public.get("active_profile_id") or ""),
        active_profile_name=str(public.get("active_profile_name") or "Default"),
        profiles=profiles,
        focus_profile_id=str(focus) if focus else None,
    )


def _resolve_translation_ai_saved(
    service: WorkspaceSettingsService,
    workspace_id: UUID,
    profile_id: str | None,
    settings_key: str,
) -> TranslationAiConfig:
    """Load saved config either from a specific profile or the active profile."""
    pid = (profile_id or "").strip()
    if pid:
        workspace = service._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        _aid, profiles = service._normalize_llm_ai_profiles(raw)
        target = service._find_tts_profile(profiles, pid)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile_not_found")
        return service._parse_translation_ai(target)
    if settings_key == "caption_ai":
        return service.get_caption_ai(workspace_id)
    return service.get_translation_ai(workspace_id)


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


@router.post("/translation-ai/profiles", response_model=TranslationAiResponse)
def create_translation_ai_profile(
    body: TranslationAiProfileCreateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        created = service.create_translation_ai_profile(workspace_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=str(created.get("id") or ""))


@router.put("/translation-ai/profiles/reorder", response_model=TranslationAiResponse)
def reorder_translation_ai_profiles(
    body: ProfileReorderRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.reorder_translation_ai_profiles(workspace_id, body.profile_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _translation_ai_response(public, updated=True)


@router.get("/translation-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def get_translation_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.get_translation_ai_profile_public(workspace_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _translation_ai_response(public)


@router.put("/translation-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def put_translation_ai_profile(
    profile_id: str,
    body: TranslationAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_translation_ai_profile(
            workspace_id,
            profile_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.patch("/translation-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def patch_translation_ai_profile(
    profile_id: str,
    body: TranslationAiProfilePatchRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        if body.name is not None:
            service.rename_translation_ai_profile(workspace_id, profile_id, name=body.name)
        if body.enabled is not None:
            service.set_translation_ai_profile_enabled(workspace_id, profile_id, enabled=body.enabled)
        if body.name is None and body.enabled is None:
            raise ValueError("empty_patch")
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.post("/translation-ai/profiles/{profile_id}/activate", response_model=TranslationAiResponse)
def activate_translation_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.activate_translation_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public)


@router.delete("/translation-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def delete_translation_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.delete_translation_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_translation_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True)


@router.post("/translation-ai/test", response_model=TranslationAiTestResponse)
def test_translation_ai(
    body: TranslationAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiTestResponse:
    service = WorkspaceSettingsService(db)
    saved = _resolve_translation_ai_saved(service, workspace_id, body.profile_id, "translation_ai")
    draft = body.model_dump(exclude_none=True, exclude={"profile_id"})
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
            region=str(body.region if body.region is not None else saved.region),
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
    saved = _resolve_translation_ai_saved(service, workspace_id, body.profile_id, "translation_ai")
    provider = str(body.provider or saved.provider or "auto").strip().lower()
    api_key = _resolve_translation_ai_draft_key(
        saved=saved,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
    )
    base_url = str(body.base_url if body.base_url is not None else saved.base_url or "")
    region = str(body.region if body.region is not None else saved.region or "global")
    timeout = float(body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds or 30.0)
    ok, models, detail = list_translation_ai_models(
        provider=provider,
        api_key=api_key or "",
        base_url=base_url,
        region=region,
        timeout_seconds=list_models_timeout_seconds(timeout),
    )
    return TranslationAiModelsResponse(ok=ok, provider=provider, models=models, detail=detail)


# --- Caption AI settings (Phase 2.5 hard-sub) — separate from Translation settings ---


@router.get("/caption-prompt", response_model=TranslationPromptResponse)
def get_caption_prompt(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    public = WorkspaceSettingsService(db).get_caption_prompt_public(workspace_id)
    return _prompt_response(public)


@router.put("/caption-prompt", response_model=TranslationPromptResponse)
def put_caption_prompt(
    body: TranslationPromptUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.set_caption_prompt(workspace_id, body.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_caption_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


@router.post("/caption-prompt/profiles", response_model=TranslationPromptResponse)
def create_caption_prompt_profile(
    body: PromptProfileCreateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        created = service.create_caption_prompt_profile(workspace_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_caption_prompt_public(workspace_id)
    return _prompt_response(public, updated=True, focus_profile_id=str(created.get("id") or ""))


@router.put("/caption-prompt/profiles/reorder", response_model=TranslationPromptResponse)
def reorder_caption_prompt_profiles(
    body: ProfileReorderRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.reorder_caption_prompt_profiles(workspace_id, body.profile_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _prompt_response(public, updated=True)


@router.get("/caption-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def get_caption_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.get_caption_prompt_profile_public(workspace_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _prompt_response(public)


@router.put("/caption-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def put_caption_prompt_profile(
    profile_id: str,
    body: PromptProfileUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.set_caption_prompt_profile(workspace_id, profile_id, prompt=body.prompt)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_caption_prompt_profile_public(workspace_id, profile_id)
    return _prompt_response(public, updated=True, focus_profile_id=profile_id)


@router.patch("/caption-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def patch_caption_prompt_profile(
    profile_id: str,
    body: PromptProfilePatchRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        if body.name is None:
            raise ValueError("empty_patch")
        service.rename_caption_prompt_profile(workspace_id, profile_id, name=body.name)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_caption_prompt_profile_public(workspace_id, profile_id)
    return _prompt_response(public, updated=True, focus_profile_id=profile_id)


@router.post(
    "/caption-prompt/profiles/{profile_id}/activate",
    response_model=TranslationPromptResponse,
)
def activate_caption_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.activate_caption_prompt_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_caption_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


@router.delete("/caption-prompt/profiles/{profile_id}", response_model=TranslationPromptResponse)
def delete_caption_prompt_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationPromptResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.delete_caption_prompt_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=_prompt_value_error_code(detail), detail=detail) from exc
    public = service.get_caption_prompt_public(workspace_id)
    return _prompt_response(public, updated=True)


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


@router.post("/caption-ai/profiles", response_model=TranslationAiResponse)
def create_caption_ai_profile(
    body: TranslationAiProfileCreateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        created = service.create_caption_ai_profile(workspace_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=str(created.get("id") or ""))


@router.put("/caption-ai/profiles/reorder", response_model=TranslationAiResponse)
def reorder_caption_ai_profiles(
    body: ProfileReorderRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.reorder_caption_ai_profiles(workspace_id, body.profile_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _translation_ai_response(public, updated=True)


@router.get("/caption-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def get_caption_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.get_caption_ai_profile_public(workspace_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _translation_ai_response(public)


@router.put("/caption-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def put_caption_ai_profile(
    profile_id: str,
    body: TranslationAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_caption_ai_profile(
            workspace_id,
            profile_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.patch("/caption-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def patch_caption_ai_profile(
    profile_id: str,
    body: TranslationAiProfilePatchRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        if body.name is not None:
            service.rename_caption_ai_profile(workspace_id, profile_id, name=body.name)
        if body.enabled is not None:
            service.set_caption_ai_profile_enabled(workspace_id, profile_id, enabled=body.enabled)
        if body.name is None and body.enabled is None:
            raise ValueError("empty_patch")
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.post("/caption-ai/profiles/{profile_id}/activate", response_model=TranslationAiResponse)
def activate_caption_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.activate_caption_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public)


@router.delete("/caption-ai/profiles/{profile_id}", response_model=TranslationAiResponse)
def delete_caption_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.delete_caption_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_caption_ai_public(workspace_id)
    return _translation_ai_response(public, updated=True)


@router.post("/caption-ai/test", response_model=TranslationAiTestResponse)
def test_caption_ai(
    body: TranslationAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TranslationAiTestResponse:
    service = WorkspaceSettingsService(db)
    saved = _resolve_translation_ai_saved(service, workspace_id, body.profile_id, "caption_ai")
    draft = body.model_dump(exclude_none=True, exclude={"profile_id"})
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
            region=str(body.region if body.region is not None else saved.region),
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
    saved = _resolve_translation_ai_saved(service, workspace_id, body.profile_id, "caption_ai")
    provider = str(body.provider or saved.provider or "auto").strip().lower()
    api_key = _resolve_translation_ai_draft_key(
        saved=saved,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
    )
    base_url = str(body.base_url if body.base_url is not None else saved.base_url or "")
    region = str(body.region if body.region is not None else saved.region or "global")
    timeout = float(body.timeout_seconds if body.timeout_seconds is not None else saved.timeout_seconds or 30.0)
    ok, models, detail = list_translation_ai_models(
        provider=provider,
        api_key=api_key or "",
        base_url=base_url,
        region=region,
        timeout_seconds=list_models_timeout_seconds(timeout),
    )
    return TranslationAiModelsResponse(ok=ok, provider=provider, models=models, detail=detail)


def _tts_ai_response(public: dict, *, updated: bool = False, focus_profile_id: str | None = None) -> TtsAiResponse:
    runtime_raw = public.get("runtime") or {}
    runtime = TtsAiRuntime.model_validate(normalize_runtime(runtime_raw))
    profiles_raw = public.get("profiles") or []
    profiles = [TtsAiProfileSummary.model_validate(item) for item in profiles_raw]
    focus = focus_profile_id if focus_profile_id is not None else public.get("focus_profile_id")
    return TtsAiResponse(
        enabled=bool(public.get("enabled")),
        provider=str(public.get("provider") or "auto"),
        voice_id=str(public.get("voice_id") or ""),
        speaking_rate=float(public.get("speaking_rate") or 1.0),
        language_code=str(public.get("language_code") or "vi"),
        model_id=str(public.get("model_id") or ""),
        api_key_set=bool(public.get("api_key_set")),
        api_key_masked=str(public.get("api_key_masked") or ""),
        credential_mode=str(public.get("credential_mode") or "api_key"),
        google_service_account_set=bool(public.get("google_service_account_set")),
        google_service_account_email=str(public.get("google_service_account_email") or ""),
        google_service_account_project_id=str(
            public.get("google_service_account_project_id") or ""
        ),
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
        active_profile_id=str(public.get("active_profile_id") or ""),
        active_profile_name=str(public.get("active_profile_name") or "Default"),
        profiles=profiles,
        focus_profile_id=str(focus) if focus else None,
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


@router.post("/tts-ai/profiles", response_model=TtsAiResponse)
def create_tts_ai_profile(
    body: TtsAiProfileCreateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    """Create a blank TTS setup without changing the active setup."""
    service = WorkspaceSettingsService(db)
    try:
        created = service.create_tts_ai_profile(workspace_id, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public, updated=True, focus_profile_id=str(created.get("id") or ""))


@router.put("/tts-ai/profiles/reorder", response_model=TtsAiResponse)
def reorder_tts_ai_profiles(
    body: ProfileReorderRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.reorder_tts_ai_profiles(workspace_id, body.profile_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _tts_ai_response(public, updated=True)


@router.get("/tts-ai/profiles/{profile_id}", response_model=TtsAiResponse)
def get_tts_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        public = service.get_tts_ai_profile_public(workspace_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _tts_ai_response(public)


@router.put("/tts-ai/profiles/{profile_id}", response_model=TtsAiResponse)
def put_tts_ai_profile(
    profile_id: str,
    body: TtsAiUpdateRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    """Save connection fields for one setup. Does not change active or overview on/off."""
    service = WorkspaceSettingsService(db)
    keep_key = body.api_key is None and not body.clear_api_key
    payload = body.model_dump()
    try:
        service.set_tts_ai_profile(
            workspace_id,
            profile_id,
            payload,
            keep_existing_api_key=keep_key,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.patch("/tts-ai/profiles/{profile_id}", response_model=TtsAiResponse)
def patch_tts_ai_profile(
    profile_id: str,
    body: TtsAiProfilePatchRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    """Rename and/or toggle enabled from the overview list."""
    service = WorkspaceSettingsService(db)
    try:
        if body.name is not None:
            service.rename_tts_ai_profile(workspace_id, profile_id, name=body.name)
        if body.enabled is not None:
            service.set_tts_ai_profile_enabled(workspace_id, profile_id, enabled=body.enabled)
        if body.name is None and body.enabled is None:
            raise ValueError("empty_patch")
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public, updated=True, focus_profile_id=profile_id)


@router.post("/tts-ai/profiles/{profile_id}/activate", response_model=TtsAiResponse)
def activate_tts_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.activate_tts_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "profile_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public)


@router.delete("/tts-ai/profiles/{profile_id}", response_model=TtsAiResponse)
def delete_tts_ai_profile(
    profile_id: str,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiResponse:
    service = WorkspaceSettingsService(db)
    try:
        service.delete_tts_ai_profile(workspace_id, profile_id)
    except ValueError as exc:
        detail = str(exc)
        if detail == "profile_not_found":
            code = status.HTTP_404_NOT_FOUND
        else:
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    public = service.get_tts_ai_public(workspace_id)
    return _tts_ai_response(public, updated=True)


@router.post("/tts-ai/test", response_model=TtsAiTestResponse)
def test_tts_ai(
    body: TtsAiTestRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiTestResponse:
    service = WorkspaceSettingsService(db)
    profile_id = (body.profile_id or "").strip() or None
    if profile_id:
        raw = (service._resolve_workspace(workspace_id).settings_json or {}).get("tts_ai")
        _aid, profiles = service._normalize_tts_profiles(raw)
        target = service._find_tts_profile(profiles, profile_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile_not_found")
        saved = service._parse_tts_ai(target)
    else:
        saved = service.get_tts_ai(workspace_id)
    draft = body.model_dump(exclude_none=True, exclude={"profile_id", "probe_mode"})
    if not draft and not body.clear_api_key:
        cfg = saved
    else:
        api_key = saved.api_key
        if body.clear_api_key:
            api_key = None
        elif body.api_key is not None:
            cleaned = body.api_key.strip()
            api_key = cleaned or None
        service_account_json = saved.google_service_account_json
        if body.clear_google_service_account:
            service_account_json = None
        elif body.google_service_account_json is not None:
            cleaned_service_account = body.google_service_account_json.strip()
            service_account_json = cleaned_service_account or None
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
            credential_mode=str(
                body.credential_mode if body.credential_mode is not None else saved.credential_mode
            ),
            google_service_account_json=service_account_json,
            google_service_account_email=saved.google_service_account_email,
            google_service_account_project_id=saved.google_service_account_project_id,
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
    # Agent Platform's TTS catalog is curated: models.list needs OAuth2 and a
    # catalog refresh must never spend quota or fail because synthesis is not
    # available in a project region. Keep every existing provider's discovery
    # behavior unchanged; only an explicit connection test performs the short
    # google_cloud_tts audio probe.
    discover_remote = not (
        body.probe_mode == "catalog"
        and str(getattr(cfg, "provider", "") or "").strip().lower() == "google_cloud_tts"
    )
    result = probe_tts_ai_client(cfg, discover_remote=discover_remote)
    catalog = None
    if result.catalog:
        catalog = TtsAiCatalog.model_validate(result.catalog)
    runtime = service.patch_tts_ai_runtime(
        workspace_id,
        profile_id=profile_id,
        last_probe=build_last_probe(
            ok=result.ok,
            provider=result.provider,
            detail=result.detail,
            catalog=result.catalog,
            checks=result.checks,
            config_fingerprint=str(
                ((result.catalog or {}).get("discovery") or {}).get("config_fingerprint") or ""
            ),
        ),
    )
    config_fingerprint = str(
        ((result.catalog or {}).get("discovery") or {}).get("config_fingerprint") or ""
    )
    return TtsAiTestResponse(
        ok=result.ok,
        provider=result.provider,
        detail=result.detail,
        catalog=catalog,
        runtime=TtsAiRuntime.model_validate(runtime),
        checks=result.checks,
        config_fingerprint=config_fingerprint,
    )


@router.post("/tts-ai/install", response_model=TtsAiInstallResponse)
def install_tts_ai_package(
    body: TtsAiInstallRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiInstallResponse:
    """Start allowlisted pip install in a background thread; poll GET /tts-ai/install/status."""
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

    package_name = (body.package or "").strip()
    force = bool(body.force_reinstall)
    if not force and is_tts_package_installed(plan):
        job = complete_tts_use_installed(
            workspace_id=workspace_id,
            plan=plan,
            package_name=package_name,
            provider=body.provider,
            profile_id=(body.profile_id or "").strip() or None,
        )
        _ = db
        return _tts_install_response_from_job(job)

    try:
        job = start_tts_install_job(
            workspace_id=workspace_id,
            plan=plan,
            package_name=package_name,
            provider=body.provider,
            profile_id=(body.profile_id or "").strip() or None,
            timeout_seconds=body.timeout_seconds,
            force_reinstall=force,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Touch db dependency so auth/workspace resolution stays consistent with other ops routes.
    _ = db
    return _tts_install_response_from_job(job)


@router.get("/tts-ai/engines", response_model=TtsAiEngineCatalogResponse)
def list_tts_ai_engines(
    workspace_id: UUID = Depends(get_current_workspace),
) -> TtsAiEngineCatalogResponse:
    """Return host-aware OmniVoice engine readiness without importing heavy models."""
    _ = workspace_id
    settings = get_settings()
    root = getattr(settings, "audio_tts_engine_root", "./data/tts-engines")
    return TtsAiEngineCatalogResponse(
        engines=discover_omnivoice_engines(
            managed_installed=lambda engine_id: is_managed_engine_installed(engine_id, root=root)
        )
    )


@router.post("/tts-ai/engines/{engine_id}/install", response_model=TtsAiEngineInstallJobResponse)
def install_tts_ai_engine(
    engine_id: str,
    body: TtsAiEngineInstallRequest,
    workspace_id: UUID = Depends(get_current_workspace),
) -> TtsAiEngineInstallJobResponse:
    """Start a registry-owned pip or managed-source engine install."""
    rows = {str(row["id"]): row for row in discover_omnivoice_engines()}
    row = rows.get(engine_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown OmniVoice engine")

    recipe = get_omnivoice_engine_install(engine_id)
    if recipe is None:
        hint = str(row.get("install_hint") or "This engine requires manual setup")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"One-click install is unavailable for {engine_id}. {hint}",
        )

    settings = get_settings()
    if not bool(getattr(settings, "audio_tts_allow_install", True)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TTS package install is disabled (AUDIO_TTS_ALLOW_INSTALL=false)",
        )

    try:
        payload = start_engine_install(
            workspace_id=str(workspace_id),
            recipe=recipe,
            root=getattr(settings, "audio_tts_engine_root", "./data/tts-engines"),
            force_reinstall=body.force_reinstall,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TtsAiEngineInstallJobResponse.model_validate(payload)


@router.get("/tts-ai/engines/install/status", response_model=TtsAiEngineInstallJobResponse)
def get_tts_ai_engine_install_status(
    workspace_id: UUID = Depends(get_current_workspace),
) -> TtsAiEngineInstallJobResponse:
    settings = get_settings()
    payload = get_engine_install_status(
        workspace_id=str(workspace_id),
        root=getattr(settings, "audio_tts_engine_root", "./data/tts-engines"),
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No OmniVoice engine install job")
    return TtsAiEngineInstallJobResponse.model_validate(payload)


@router.get("/tts-ai/install/status", response_model=TtsAiInstallResponse)
def get_tts_ai_install_status(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiInstallResponse:
    """Poll background TTS install job for the current workspace."""
    job = get_tts_install_job(workspace_id)
    if job is not None:
        return _tts_install_response_from_job(job)

    service = WorkspaceSettingsService(db)
    runtime_raw = service.get_tts_ai(workspace_id).runtime
    runtime = TtsAiRuntime.model_validate(normalize_runtime(runtime_raw))
    last = runtime.last_install
    if last is None:
        return TtsAiInstallResponse(
            ok=False,
            status="",
            detail="No TTS install job for this workspace",
            runtime=runtime,
        )
    status_value = (last.status or "").strip()
    if not status_value:
        status_value = "succeeded" if last.ok else "failed"
    return TtsAiInstallResponse(
        ok=bool(last.ok),
        status=status_value,
        detail=last.detail,
        command=last.command,
        log_tail="",
        already_satisfied=bool(last.already_satisfied),
        runtime=runtime,
    )


def _tts_preview_response_from_job(job) -> TtsAiPreviewResponse:
    return TtsAiPreviewResponse(
        ok=bool(job.ok),
        status=job.status,
        provider=job.provider,
        detail=job.detail,
        mime_type=job.mime_type or "audio/wav",
        duration_seconds=float(job.duration_seconds or 0.0),
        audio_base64=job.audio_base64 or "",
        warnings=list(job.warnings or []),
        text=job.text or "",
        requested_voice_id=job.requested_voice_id or "",
        resolved_voice_id=job.resolved_voice_id or "",
        requested_model_id=job.requested_model_id or "",
        resolved_model_id=job.resolved_model_id or "",
    )


@router.post("/tts-ai/preview", response_model=TtsAiPreviewResponse)
def preview_tts_ai_speech(
    body: TtsAiPreviewRequest,
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiPreviewResponse:
    """Start background speech preview; poll GET /tts-ai/preview/status.

    Local models (OmniVoice) may download weights on first run — keeping the
    Next.js /api rewrite open that long previously returned an opaque HTTP 500.
    """
    service = WorkspaceSettingsService(db)
    profile_id = (body.profile_id or "").strip() or None
    if profile_id:
        raw = (service._resolve_workspace(workspace_id).settings_json or {}).get("tts_ai")
        _active_id, profiles = service._normalize_tts_profiles(raw)
        target = service._find_tts_profile(profiles, profile_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile_not_found")
        saved = service._parse_tts_ai(target)
    else:
        saved = service.get_tts_ai(workspace_id)
    api_key = saved.api_key
    if body.clear_api_key:
        api_key = None
    elif body.api_key is not None:
        cleaned = body.api_key.strip()
        api_key = cleaned or None
    service_account_json = saved.google_service_account_json
    if body.clear_google_service_account:
        service_account_json = None
    elif body.google_service_account_json is not None:
        cleaned_service_account = body.google_service_account_json.strip()
        service_account_json = cleaned_service_account or None
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
        credential_mode=str(
            body.credential_mode if body.credential_mode is not None else saved.credential_mode
        ),
        google_service_account_json=service_account_json,
        google_service_account_email=saved.google_service_account_email,
        google_service_account_project_id=saved.google_service_account_project_id,
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
        job = start_tts_preview_job(
            workspace_id=workspace_id,
            workspace_tts=cfg,
            text=body.text,
            max_chars=body.max_chars,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _tts_preview_response_from_job(job)


@router.get("/tts-ai/preview/status", response_model=TtsAiPreviewResponse)
def get_tts_ai_preview_status(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiPreviewResponse:
    """Poll background TTS preview job for the current workspace."""
    _ = db
    job = get_tts_preview_job(workspace_id)
    if job is None:
        return TtsAiPreviewResponse(
            ok=False,
            status="",
            detail="No TTS preview job for this workspace",
        )
    return _tts_preview_response_from_job(job)


@router.post("/tts-ai/preview/cancel", response_model=TtsAiPreviewResponse)
def cancel_tts_ai_preview(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> TtsAiPreviewResponse:
    """Cancel a running preview so the operator can start again."""
    _ = db
    job = cancel_tts_preview_job(workspace_id)
    if job is None:
        return TtsAiPreviewResponse(
            ok=False,
            status="cancelled",
            detail="No TTS preview job for this workspace",
        )
    return _tts_preview_response_from_job(job)
