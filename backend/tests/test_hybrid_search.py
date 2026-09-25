import pytest
from app.services import hybrid_search as hybrid_module
from app.services.hybrid_search import (
    HybridResult,
    fuse_rrf,
    fusion_pool_size,
    normalize_channels,
    search_hybrid,
)


def test_normalize_channels_defaults_unknown_to_hybrid() -> None:
    assert normalize_channels("foo") == "hybrid"
    assert normalize_channels("vector") == "vector"


def test_fusion_pool_size_doubles_with_floor() -> None:
    assert fusion_pool_size(5) == 10
    assert fusion_pool_size(8) == 16


def test_fuse_rrf_scores_shared_hits_highest() -> None:
    fused = fuse_rrf([[2, 1, 3], [2, 4, 1]])

    assert fused[2] > fused[1] > fused[4]
    assert fused[2] == pytest.approx(1 / 61 + 1 / 61)


def test_fuse_rrf_empty_channels() -> None:
    assert fuse_rrf([]) == {}
    assert fuse_rrf([[], []]) == {}


def _hit(chunk_id: int, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "kb_id": 1,
        "chunk_index": chunk_id,
        "content": f"内容{chunk_id}",
        "score": score,
        "section_path": "课程",
    }


def test_search_hybrid_fuses_both_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [
            _hit(2, 0.8), _hit(1, 0.9),
        ]
    )
    monkeypatch.setattr(
        hybrid_module, "search_lexical",
        lambda db, kb_id, query, top_k: ([_hit(2, 1.0), _hit(3, 0.5)], {"returned": 2, "best": 1.0, "fallback": None}),
    )

    result = search_hybrid(object(), kb_id=1, query="测试", top_k=2, channels="hybrid")

    assert isinstance(result, HybridResult)
    assert [hit["chunk_id"] for hit in result.hits] == [2, 1]
    assert result.hits[0]["score"] == pytest.approx(1.0)
    assert result.trace["mode"] == "hybrid"
    assert result.trace["fused_by"] == "rrf_k60"
    assert result.trace["vector"]["returned"] == 2
    assert result.trace["lexical"]["returned"] == 2


def test_search_hybrid_single_channel_modes(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )

    vector_only = search_hybrid(None, kb_id=1, query="测试", top_k=5, channels="vector")

    assert [hit["chunk_id"] for hit in vector_only.hits] == [1]
    assert vector_only.hits[0]["score"] == 0.9
    assert vector_only.trace["lexical"]["skipped"] is True


def test_search_hybrid_normalizes_unknown_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )
    monkeypatch.setattr(
        hybrid_module, "search_lexical",
        lambda db, kb_id, query, top_k: ([], {"returned": 0, "best": 0.0, "fallback": None}),
    )

    result = search_hybrid(object(), kb_id=1, query="测试", top_k=5, channels="bogus")

    assert result.trace["mode"] == "hybrid"


def test_search_hybrid_skips_lexical_without_db(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )

    result = search_hybrid(None, kb_id=1, query="测试", top_k=5, channels="hybrid")

    assert [hit["chunk_id"] for hit in result.hits] == [1]
    assert result.trace["lexical_skipped"] == "no_db"
