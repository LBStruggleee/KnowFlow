from typing import Any

from app.models.document_chunk import DocumentChunk
from app.services.lexical_search import search_lexical
from app.services.vector_store_service import vector_store_service
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

RRF_K = 60
VALID_CHANNELS = ("vector", "lexical", "hybrid")
INJECTION_MODES = ("off", "downweight", "exclude")
DEFAULT_INJECTION_MODE = "downweight"
DEFAULT_INJECTION_DOWNWEIGHT = 0.5

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


def normalize_injection_mode(mode: str) -> str:
    return mode if mode in INJECTION_MODES else DEFAULT_INJECTION_MODE


def _flagged_chunk_ids(db: Session | None, chunk_ids: list[int]) -> set[int]:
    # ``isinstance`` keeps callers that pass a sentinel (tests) or None from
    # reaching into a session they do not really have; production always passes
    # a real Session.
    if db is None or not isinstance(db, Session) or not chunk_ids:
        return set()
    rows = db.scalars(
        select(DocumentChunk.id).where(
            DocumentChunk.id.in_(chunk_ids),
            DocumentChunk.injection_flag.is_(True),
        )
    )
    return {int(chunk_id) for chunk_id in rows}


def apply_injection_policy(
    db: Session | None,
    hits: list[dict[str, Any]],
    mode: str,
    downweight: float,
) -> tuple[list[dict[str, Any]], int]:
    """Downweight or exclude chunks flagged by the ingestion-time screen.

    Runs after fusion and before the top-k slice so an excluded hit can be
    replaced by the next candidate instead of silently shrinking the result.
    Returns the adjusted hits (re-sorted when downweighting) and how many
    returned candidates were affected.
    """
    policy = normalize_injection_mode(mode)
    if not hits or policy == "off":
        return list(hits), 0

    flagged = _flagged_chunk_ids(db, [int(hit["chunk_id"]) for hit in hits])
    if not flagged:
        return list(hits), 0

    if policy == "exclude":
        kept = [hit for hit in hits if int(hit["chunk_id"]) not in flagged]
        return kept, len(hits) - len(kept)

    adjusted = [
        {**hit, "score": float(hit["score"]) * downweight}
        if int(hit["chunk_id"]) in flagged
        else hit
        for hit in hits
    ]
    adjusted.sort(key=lambda hit: float(hit["score"]), reverse=True)
    return adjusted, sum(1 for hit in hits if int(hit["chunk_id"]) in flagged)


def search_hybrid(
    db: Session | None,
    kb_id: int,
    query: str,
    top_k: int = 5,
    channels: str = "hybrid",
    injection_mode: str = DEFAULT_INJECTION_MODE,
    injection_downweight: float = DEFAULT_INJECTION_DOWNWEIGHT,
) -> HybridResult:
    mode = normalize_channels(channels)
    policy = normalize_injection_mode(injection_mode)
    pool = fusion_pool_size(top_k)
    vector_hits: list[dict[str, Any]] = []
    lexical_hits: list[dict[str, Any]] = []
    lexical_info: dict[str, Any] = {"returned": 0, "best": 0.0}
    trace: dict[str, Any] = {"mode": mode, "fused_by": "rrf_k60"}
    trace["injection"] = {"mode": policy, "downweight": injection_downweight, "flagged": 0}

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
        hits, flagged = apply_injection_policy(db, vector_hits, policy, injection_downweight)
        trace["injection"]["flagged"] = flagged
        return HybridResult(hits=hits[:top_k], trace=trace)
    if mode == "lexical" or (mode == "hybrid" and not vector_hits):
        trace["score_semantics"] = LEXICAL_SEMANTICS
        hits, flagged = apply_injection_policy(db, lexical_hits, policy, injection_downweight)
        trace["injection"]["flagged"] = flagged
        return HybridResult(hits=hits[:top_k], trace=trace)

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
    fused_hits = [{**by_id[chunk_id], "score": fused[chunk_id] / divisor} for chunk_id in ordered]
    hits, flagged = apply_injection_policy(db, fused_hits, policy, injection_downweight)
    trace["injection"]["flagged"] = flagged
    return HybridResult(hits=hits[:top_k], trace=trace)
