from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Harden before any OCR/Paddle import on Windows (Paddle 3.3.x oneDNN/PIR).
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_onednn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

from src.api.routes.analytics import router as analytics_router
from src.api.routes.affiliate_intelligence import router as affiliate_intelligence_router
from src.api.routes.affiliate_intelligence import public_router as affiliate_intelligence_public_router
from src.api.routes.affiliate_comments import router as affiliate_comments_router
from src.api.routes.auth import router as auth_router
from src.api.routes.audio_analysis import router as audio_analysis_router
from src.api.routes.candidates import router as candidates_router
from src.api.routes.content_intelligence import router as content_intelligence_router
from src.api.routes.growth_intelligence import router as growth_intelligence_router
from src.api.routes.capture_inbox import public_router as capture_inbox_public_router
from src.api.routes.capture_inbox import router as capture_inbox_router
from src.api.routes.downloads import router as downloads_router
from src.api.routes.douyin_accounts import router as douyin_accounts_router
from src.api.routes.douyin_extension import router as douyin_extension_router
from src.api.routes.internal_douyin_download import router as internal_douyin_download_router
from src.api.routes.intake import router as intake_router
from src.api.routes.export_handoff import router as export_handoff_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.operations import router as operations_router
from src.api.routes.ops_home import router as ops_home_router
from src.api.routes.optimization import router as optimization_router
from src.api.routes.ocr import router as ocr_router
from src.api.routes.operator_home import router as operator_home_router
from src.api.routes.pipeline_dashboard import router as pipeline_dashboard_router
from src.api.routes.publish import router as publish_router
from src.api.routes.publish_control import router as publish_control_router
from src.api.routes.renders import router as renders_router
from src.api.routes.reup_queue import router as reup_queue_router
from src.api.routes.risk import router as risk_router
from src.api.routes.source_ingest import router as source_ingest_router
from src.api.routes.tts import router as tts_router
from src.core.auth import get_current_principal
from src.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="reup-douyin API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    protected_dependencies = [Depends(get_current_principal)] if settings.api_auth_required else []
    protected_routers = [
        affiliate_intelligence_router,
        affiliate_comments_router,
        analytics_router,
        audio_analysis_router,
        candidates_router,
        content_intelligence_router,
        growth_intelligence_router,
        capture_inbox_router,
        downloads_router,
        douyin_accounts_router,
        douyin_extension_router,
        intake_router,
        export_handoff_router,
        jobs_router,
        operations_router,
        ops_home_router,
        optimization_router,
        ocr_router,
        operator_home_router,
        pipeline_dashboard_router,
        publish_control_router,
        publish_router,
        renders_router,
        reup_queue_router,
        risk_router,
        source_ingest_router,
        tts_router,
    ]

    app.include_router(auth_router)
    app.include_router(capture_inbox_public_router)
    app.include_router(affiliate_intelligence_public_router)
    app.include_router(internal_douyin_download_router)
    for router in protected_routers:
        app.include_router(router, dependencies=protected_dependencies)
    return app


app = create_app()
