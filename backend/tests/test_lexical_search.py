from app.services.lexical_search import _build_search_text, to_search_text


def test_to_search_text_bigrams_chinese() -> None:
    assert to_search_text("混合检索") == "混合 合检 检索"


def test_to_search_text_handles_mixed_chinese_ascii() -> None:
    assert to_search_text("HDFS的NameNode节点") == "HDFS NameNode 节点"


def test_to_search_text_drops_punctuation_and_single_chars() -> None:
    assert to_search_text("你好，世界！") == "你好 世界"
    assert to_search_text("是的") == "是的"


def test_to_search_text_returns_empty_for_blank_or_symbol_input() -> None:
    assert to_search_text("") == ""
    assert to_search_text("  !!!???  ") == ""


def test_to_search_text_keeps_ascii_words_whole() -> None:
    assert to_search_text("MapReduce Shuffle") == "MapReduce Shuffle"


def test_build_search_text_combines_content_and_section_path() -> None:
    assert _build_search_text("背景正文", "课程 / 第一章") == "背景 景正 正文 课程 第一 一章"
    assert _build_search_text("背景正文") == "背景 景正 正文"
