import logging
import sys

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.learning_records import router as learning_records_router
from app.api.vector_search import router as vector_search_router
from app.core.config import settings
from app.core.database import BASE_DIR, Base, SessionLocal, engine
from app.core.migrations import run_migrations
from app.services.startup_recovery import reconcile_orphan_vectors, recover_interrupted_documents
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _running_under_pytest() -> bool:
    # Startup vector maintenance must not touch the developer's real
    # Chroma storage merely because the test suite imports this module.
    return "pytest" in sys.modules


def create_app() -> FastAPI:
    application = FastAPI(
        title="KnowFlow API",
        description="KnowFlow（知汇）——通用知识库 RAG 问答平台的后端 API",
        version="0.3.0",
    )

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with SessionLocal() as db:
        recover_interrupted_documents(db)
        if not _running_under_pytest():
            reconcile_orphan_vectors(db)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    application.include_router(health_router)
    application.include_router(knowledge_bases_router)
    application.include_router(documents_router)
    application.include_router(vector_search_router)
    application.include_router(chat_router)
    application.include_router(conversations_router)
    application.include_router(learning_records_router)
    application.include_router(admin_router)

    # Same-origin deployment (evaluation R-04): when the SPA has been built,
    # serve frontend/dist from this process so API and UI share one origin and
    # no CORS configuration is needed. The mount is registered last, so every
    # API route (and /docs) keeps precedence over the static fallback; the JSON
    # welcome root is only used when there is no built frontend to serve.
    frontend_dist = BASE_DIR.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        application.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:

        @application.get("/")
        def root() -> dict[str, str]:
            return {
                "message": "Welcome to KnowFlow API",
                "docs": "/docs",
                "health": "/api/health",
            }

    return application


app = create_app()
