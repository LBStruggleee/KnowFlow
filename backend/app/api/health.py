from app.services.embedding_service import embedding_status
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str | bool | int]:
    index_status = vector_store_service.index_status()
    return {
        "status": "ok",
        "service": "KnowFlow backend",
        **embedding_status(),
        "vector_collection": vector_store_service.collection_name,
        # Flat fields keep the probe endpoint simple; /api/admin/providers
        # carries the full per-collection breakdown.
        "vector_index_active_chunks": int(index_status["active_chunks"]),
        "vector_index_stale_chunks": int(index_status["stale_chunks"]),
        "vector_index_stale": bool(index_status["index_stale"]),
    }
