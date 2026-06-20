from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.vector_search import router as vector_search_router
from app.core.database import Base, engine
from app import models

app = FastAPI(
    title="KnowFlow API",
    description="KnowFlow（知汇）面向大数据学习场景的 RAG 问答平台后端 API",
    version="0.1.0",
)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(knowledge_bases_router)
app.include_router(documents_router)
app.include_router(vector_search_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Welcome to KnowFlow API",
        "docs": "/docs",
        "health": "/api/health",
    }
