import pytest
from app.services.text_chunker import estimate_token_count, split_text


def test_split_text_returns_empty_for_blank_input() -> None:
    assert split_text("  \n\n ") == []


def test_split_text_splits_long_text_with_overlap() -> None:
    chunks = split_text("abcdefghij", chunk_size=6, chunk_overlap=2)

    assert chunks == ["abcdef", "efghij"]


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_split_text_rejects_invalid_limits(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    with pytest.raises(ValueError):
        split_text("content", chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def test_estimate_token_count_handles_chinese_and_ascii() -> None:
    assert estimate_token_count("中文abcd") == 3
