"""Hybrid retrieval endpoint.

Despite the historical ``/search`` path, this endpoint does not run a
vector-only query: it dispatches through the configured retrieval channels
(vector, lexical, or hybrid, per the ``retrieval_channels`` setting) and
fuses ranked results with RRF. The route path is kept for compatibility.
"""

from app.core.database import get_db
from app.core.db_utils import get_knowledge_base_or_404
from app.schemas.vector_search import VectorSearchRequest, VectorSearchResponse
from app.services.hybrid_search import search_hybrid
from app.services.settings_service import typed_settings
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/kbs", tags=["hybrid search"])


@router.post("/{kb_id}/search", response_model=VectorSearchResponse)
def search_knowledge_base(
    kb_id: int,
    payload: VectorSearchRequest,
    db: Session = Depends(get_db),
) -> VectorSearchResponse:
    get_knowledge_base_or_404(db, kb_id)

    config = typed_settings(db)
    hybrid = search_hybrid(
        db,
        kb_id=kb_id,
        query=payload.query,
        top_k=payload.top_k,
        channels=str(config["retrieval_channels"]),
    )
    return VectorSearchResponse(query=payload.query, results=hybrid.hits)
