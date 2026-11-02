import pytest
from app.services.eval.metrics import (
    hit_rate_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
    variant_consistency_at_k,
)


def test_recall_at_k_counts_only_relevant_ids() -> None:
    retrieved = ["a", "b", "c", "d"]
    relevant = {"a", "d"}

    assert recall_at_k(retrieved, relevant, k=4) == 1.0
    assert recall_at_k(retrieved, relevant, k=1) == 0.5
    assert recall_at_k(retrieved, relevant, k=2) == 0.5


def test_recall_at_k_without_relevant_ids_is_zero() -> None:
    assert recall_at_k(["a"], set(), k=3) == 0.0


def test_hit_rate_is_binary() -> None:
    assert hit_rate_at_k(["x", "a"], {"a"}, k=2) == 1.0
    assert hit_rate_at_k(["x", "a"], {"a"}, k=1) == 0.0
    assert hit_rate_at_k(["a"], {"b"}, k=5) == 0.0


def test_reciprocal_rank_uses_first_relevant_position() -> None:
    assert reciprocal_rank(["x", "a", "b"], {"a", "b"}) == 0.5
    assert reciprocal_rank(["a"], {"a"}) == 1.0
    assert reciprocal_rank(["x"], {"a"}) == 0.0


def test_ndcg_binary_prefers_relevant_at_top() -> None:
    relevant = {"a"}

    assert ndcg_at_k(["a", "b"], relevant, k=2) == 1.0
    assert ndcg_at_k(["b", "a"], relevant, k=2) == pytest.approx(1 / 1.5849625007211562)
    assert ndcg_at_k(["b", "a"], relevant, k=1) == 0.0


def test_ndcg_handles_graded_relevance() -> None:
    relevance = {"a": 2.0, "b": 1.0}

    # rank 1 discount is 1.0, rank 2 discount is log2(3)
    expected = (1.0 + 2.0 / 1.5849625007211562) / (2.0 + 1.0 / 1.5849625007211562)
    assert ndcg_at_k(["b", "a"], relevance, k=2) == pytest.approx(expected)


def test_ndcg_is_zero_without_graded_gain() -> None:
    assert ndcg_at_k(["a", "b"], {"a": 0.0}, k=2) == 0.0


@pytest.mark.parametrize(
    "metric",
    [
        lambda retrieved, relevant: recall_at_k(retrieved, relevant, k=0),
        lambda retrieved, relevant: hit_rate_at_k(retrieved, relevant, k=-1),
        lambda retrieved, relevant: ndcg_at_k(retrieved, relevant, k=0),
        lambda retrieved, relevant: variant_consistency_at_k([retrieved], relevant, k=0),
    ],
)
def test_metrics_reject_non_positive_k(metric) -> None:
    with pytest.raises(ValueError):
        metric(["a"], {"a"})


def test_refusal_accuracy_matches_decision_pairs() -> None:
    assert refusal_accuracy([True, False, True], [True, False, False]) == pytest.approx(2 / 3)
    assert refusal_accuracy([False], [False]) == 1.0


def test_refusal_accuracy_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        refusal_accuracy([True], [True, False])


def test_refusal_accuracy_on_empty_input_is_zero() -> None:
    assert refusal_accuracy([], []) == 0.0


def test_variant_consistency_counts_hitting_variants() -> None:
    hits = [["a"], ["x", "b"], ["y"]]
    relevant = {"a", "b"}

    assert variant_consistency_at_k(hits, relevant, k=2) == pytest.approx(2 / 3)
    assert variant_consistency_at_k(hits, relevant, k=1) == pytest.approx(1 / 3)
    assert variant_consistency_at_k([], relevant, k=1) == 0.0


def test_metrics_accept_integer_ids() -> None:
    assert recall_at_k([3, 1, 2], {1, 3}, k=2) == 1.0
    assert ndcg_at_k([3, 1], {1: 1.0, 3: 1.0}, k=2) == 1.0
