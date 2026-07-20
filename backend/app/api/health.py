from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "KnowFlow backend",
        "embedding_provider": vector_store_service.embedding_provider,
        "vector_collection": vector_store_service.collection_name,
    }
