from app.services.embedding_service import embedding_status
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "KnowFlow backend",
        **embedding_status(),
        "vector_collection": vector_store_service.collection_name,
    }
