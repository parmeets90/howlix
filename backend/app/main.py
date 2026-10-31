from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.media import router as media_router
from app.api.exports import router as exports_router
from app.api.moments import router as moments_router
from app.api.projects import router as projects_router
from app.api.transcripts import router as transcripts_router
from app.api.uploads import router as uploads_router
from app.config import get_settings
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Howlix API",
        description="Local API for Howlix projects, transcription, moment discovery, and private clip exports.",
        version="0.5.0",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "howlix-api"}

    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(media_router, prefix="/api/v1")
    app.include_router(transcripts_router, prefix="/api/v1")
    app.include_router(moments_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
    return app


app = create_app()

