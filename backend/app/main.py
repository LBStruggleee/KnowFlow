import logging

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.learning_records import router as learning_records_router
from app.api.vector_search import router as vector_search_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.services.lexical_search import (
    backfill_search_text,
    ensure_chunk_columns,
    ensure_lexical_index,
)
from app.services.startup_recovery import recover_interrupted_documents
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    application = FastAPI(
        title="KnowFlow API",
        description="KnowFlow（知汇）面向大数据学习场景的 RAG 问答平台后端 API",
        version="0.2.0",
    )

    Base.metadata.create_all(bind=engine)
    ensure_chunk_columns(engine)
    ensure_lexical_index(engine)
    with SessionLocal() as db:
        backfill_search_text(db)
        recover_interrupted_documents(db)
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

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "message": "Welcome to KnowFlow API",
            "docs": "/docs",
            "health": "/api/health",
        }

    return application


app = create_app()
