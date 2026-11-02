"""Pure retrieval metrics for the offline evaluation harness.

Relevance is expressed either as a collection of relevant ids (binary gain
1.0) or as a ``{id: gain}`` mapping for graded labels. Retrieved sequences are
ordered from most to least relevant, which is what every search channel in
KnowFlow already returns after fusion.

Undefined cases are pinned explicitly instead of returning ``math.nan`` so that
reports stay comparable between runs:

* an empty relevance set yields ``0.0`` for the position-aware metrics (there
  is nothing a ranker could have retrieved; refusal accuracy is the metric that
  covers "the corpus has no answer");
* ``k`` must be positive, otherwise ``ValueError``.
"""

import math
from collections.abc import Collection, Mapping, Sequence

type Relevance[IdT] = Collection[IdT] | Mapping[IdT, float]


def _validate_k(k: int) -> None:
    if k <= 0:
        raise ValueError("k must be greater than 0.")


def _gain_of[IdT](doc_id: IdT, relevant: Relevance[IdT]) -> float:
    if isinstance(relevant, Mapping):
        return float(relevant.get(doc_id, 0.0))
    return 1.0 if doc_id in relevant else 0.0


def _relevant_ids[IdT](relevant: Relevance[IdT]) -> set[IdT]:
    if isinstance(relevant, Mapping):
        return {doc_id for doc_id, gain in relevant.items() if gain > 0}
    return set(relevant)


def recall_at_k[IdT](retrieved: Sequence[IdT], relevant: Relevance[IdT], k: int) -> float:
    """Fraction of relevant ids that appear in the first ``k`` retrieved ids.

    ``relevant`` empty means no query answer exists in the corpus, which is
    measured by refusal accuracy rather than recall; the value is ``0.0``.
    """
    _validate_k(k)
    relevant_ids = _relevant_ids(relevant)
    if not relevant_ids:
        return 0.0
    found = relevant_ids.intersection(retrieved[:k])
    return len(found) / len(relevant_ids)


def hit_rate_at_k[IdT](retrieved: Sequence[IdT], relevant: Relevance[IdT], k: int) -> float:
    """``1.0`` when at least one relevant id is in the first ``k`` results."""
    _validate_k(k)
    relevant_ids = _relevant_ids(relevant)
    if not relevant_ids:
        return 0.0
    return 1.0 if relevant_ids.intersection(retrieved[:k]) else 0.0


def reciprocal_rank[IdT](retrieved: Sequence[IdT], relevant: Relevance[IdT]) -> float:
    """``1 / rank`` of the first relevant hit, or ``0.0`` when none is found."""
    relevant_ids = _relevant_ids(relevant)
    if not relevant_ids:
        return 0.0
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k[IdT](retrieved: Sequence[IdT], relevant: Relevance[IdT], k: int) -> float:
    """Normalized discounted cumulative gain with a ``log2(rank + 1)`` discount.

    With a binary relevance collection this is the standard binary nDCG; with a
    mapping it grades partial matches.
    """
    _validate_k(k)
    gains = [_gain_of(doc_id, relevant) for doc_id in retrieved[:k]]
    dcg = sum(gain / _discount(rank) for rank, gain in enumerate(gains, start=1))
    ideal_gains = _ideal_gains(relevant, k)
    if not ideal_gains:
        return 0.0
    idcg = sum(gain / _discount(rank) for rank, gain in enumerate(ideal_gains, start=1))
    return dcg / idcg


def _discount(rank: int) -> float:
    return 1.0 if rank <= 1 else math.log2(rank + 1)


def _ideal_gains[IdT](relevant: Relevance[IdT], k: int) -> list[float]:
    if isinstance(relevant, Mapping):
        return sorted((gain for gain in relevant.values() if gain > 0), reverse=True)[:k]
    return [1.0] * min(len(set(relevant)), k)


def refusal_accuracy(
    expected_answerable: Sequence[bool],
    predicted_answered: Sequence[bool],
) -> float:
    """Accuracy of the "should answer / did answer" decision.

    This is the metric that covers golden questions whose answer is absent from
    the corpus: they must produce no evidence rather than a confident hit.
    """
    if len(expected_answerable) != len(predicted_answered):
        raise ValueError("expected_answerable and predicted_answered must have equal length.")
    if not expected_answerable:
        return 0.0
    correct = sum(
        1
        for expected, predicted in zip(expected_answerable, predicted_answered, strict=True)
        if bool(expected) == bool(predicted)
    )
    return correct / len(expected_answerable)


def variant_consistency_at_k[IdT](
    hits_per_variant: Sequence[Sequence[IdT]],
    relevant: Relevance[IdT],
    k: int,
) -> float:
    """Fraction of paraphrase variants that retrieve a relevant id in the top ``k``.

    A query that only works for one exact wording is fragile; this metric makes
    that fragility visible in the baseline report.
    """
    _validate_k(k)
    relevant_ids = _relevant_ids(relevant)
    if not hits_per_variant or not relevant_ids:
        return 0.0
    consistent = sum(1 for hits in hits_per_variant if relevant_ids.intersection(hits[:k]))
    return consistent / len(hits_per_variant)
