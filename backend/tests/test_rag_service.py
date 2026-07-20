from app.services.rag_service import _build_retrieval_query, _build_retrieval_trace


def test_retrieval_trace_distinguishes_requested_and_returned_counts() -> None:
    sources = [{"score": 0.75, "chunk_id": 1}]

    trace = _build_retrieval_trace(sources, requested_top_k=5, score_threshold=0.5)

    assert trace["requested_top_k"] == 5
    assert trace["returned_count"] == 1
    assert trace["best_score"] == 0.75
    assert trace["passed_threshold"] is True


def test_retrieval_query_uses_latest_user_turn_for_reference_resolution() -> None:
    history = [
        {"role": "user", "content": "Spark RDD 是什么？"},
        {"role": "assistant", "content": "RDD 是弹性分布式数据集。"},
    ]

    query = _build_retrieval_query("它有什么特点？", history)

    assert "Spark RDD 是什么" in query
    assert "它有什么特点" in query
