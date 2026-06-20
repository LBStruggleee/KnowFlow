from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.schemas.vector_search import VectorSearchRequest, VectorSearchResponse
from app.services.vector_store_service import vector_store_service

router = APIRouter(prefix="/api/kbs", tags=["vector search"])


@router.post("/{kb_id}/search", response_model=VectorSearchResponse)
def search_knowledge_base(
    kb_id: int,
    payload: VectorSearchRequest,
    db: Session = Depends(get_db),
) -> VectorSearchResponse:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    results = vector_store_service.search(
        kb_id=kb_id,
        query=payload.query,
        top_k=payload.top_k,
    )
    return VectorSearchResponse(query=payload.query, results=results)
