from typing import Any

from app.services.lexical_search import search_lexical
from app.services.vector_store_service import vector_store_service
from pydantic import BaseModel
from sqlalchemy.orm import Session

RRF_K = 60
VALID_CHANNELS = ("vector", "lexical", "hybrid")

# Score semantics of the returned hits. score_threshold must be compared
# against a normalized [0, 1] scale, and only two of the three scales carry an
# absolute meaning:
# - vector: 1 - cosine distance, absolute in [0, 1];
# - rrf_fused: the RRF sum divided by the best possible score (top rank in
#   both channels), so a chunk ranked first everywhere scores 1.0 and a
#   single-channel top rank scores 0.5;
# - lexical: FTS bm25 is min-max normalized within the hit batch (a lone hit
#   is always 1.0) and the LIKE fallback emits pure rank positions
#   (1/(rank+1)) — batch-relative, no absolute meaning.
VECTOR_SEMANTICS = "vector_cosine"
RRF_SEMANTICS = "rrf_fused"
LEXICAL_SEMANTICS = "lexical_relative"

# Discount applied to lexical-only result sets before a score_threshold
# comparison. Without it, a single lexical hit would trivially pass any
# threshold ("单命中必过阈值" drift). With LEXICAL_ONLY_DISCOUNT = 0.5, a lone
# lexical hit gates at 0.5 — it still clears low thresholds but no longer
# pretends to be a perfect vector match; genuine multi-hit batches keep their
# relative ordering and their best hit gates at 0.5 * best.
LEXICAL_ONLY_DISCOUNT = 0.5


def threshold_score(hits: list[dict[str, Any]], score_semantics: str) -> float:
    """Best hit score on the normalized [0, 1] scale used for score_threshold."""
    best = max((float(hit["score"]) for hit in hits), default=0.0)
    if score_semantics == LEXICAL_SEMANTICS:
        return best * LEXICAL_ONLY_DISCOUNT
    return best


class HybridResult(BaseModel):
    hits: list[dict[str, Any]]
    trace: dict[str, Any]


def normalize_channels(channels: str) -> str:
    return channels if channels in VALID_CHANNELS else "hybrid"


def fusion_pool_size(top_k: int) -> int:
    return max(top_k * 2, 10)


def fuse_rrf(ranked: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in ranked:
        for rank, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return fused


def _empty_channel(skipped: Any = True) -> dict[str, Any]:
    return {"returned": 0, "best": 0.0, "skipped": skipped}


def search_hybrid(
    db: Session | None,
    kb_id: int,
    query: str,
    top_k: int = 5,
    channels: str = "hybrid",
) -> HybridResult:
    mode = normalize_channels(channels)
    pool = fusion_pool_size(top_k)
    vector_hits: list[dict[str, Any]] = []
    lexical_hits: list[dict[str, Any]] = []
    lexical_info: dict[str, Any] = {"returned": 0, "best": 0.0}
    trace: dict[str, Any] = {"mode": mode, "fused_by": "rrf_k60"}

    want_lexical = mode in ("lexical", "hybrid")
    if mode in ("vector", "hybrid"):
        vector_hits = vector_store_service.search(kb_id=kb_id, query=query, top_k=pool)
    if want_lexical and db is not None:
        lexical_hits, lexical_info = search_lexical(db, kb_id, query, pool)
    if want_lexical and db is None:
        trace["lexical_skipped"] = "no_db"

    vector_best = max((hit["score"] for hit in vector_hits), default=0.0)
    trace["vector"] = (
        {"returned": len(vector_hits), "best": vector_best}
        if mode in ("vector", "hybrid")
        else _empty_channel()
    )
    trace["lexical"] = (
        {
            "returned": lexical_info["returned"],
            "best": lexical_info["best"],
            **({"fallback": lexical_info["fallback"]} if lexical_info.get("fallback") else {}),
        }
        if want_lexical and db is not None
        else _empty_channel("no_db" if (want_lexical and db is None) else True)
    )

    if mode == "vector" or (mode == "hybrid" and not lexical_hits):
        trace["score_semantics"] = VECTOR_SEMANTICS
        return HybridResult(hits=vector_hits[:top_k], trace=trace)
    if mode == "lexical" or (mode == "hybrid" and not vector_hits):
        trace["score_semantics"] = LEXICAL_SEMANTICS
        return HybridResult(hits=lexical_hits[:top_k], trace=trace)

    by_id: dict[int, dict[str, Any]] = {}
    for hit in vector_hits:
        by_id[int(hit["chunk_id"])] = hit
    for hit in lexical_hits:
        by_id[int(hit["chunk_id"])] = hit
    rankings = [
        [int(hit["chunk_id"]) for hit in vector_hits],
        [int(hit["chunk_id"]) for hit in lexical_hits],
    ]
    fused = fuse_rrf(rankings)
    ordered = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)
    divisor = 2.0 * (1.0 / (RRF_K + 1))
    trace["score_semantics"] = RRF_SEMANTICS
    hits = [{**by_id[chunk_id], "score": fused[chunk_id] / divisor} for chunk_id in ordered[:top_k]]
    return HybridResult(hits=hits, trace=trace)
