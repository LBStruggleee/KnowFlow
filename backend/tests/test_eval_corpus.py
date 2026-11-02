import json
from pathlib import Path

import pytest
from app.services.eval.corpus import (
    EvalCase,
    case_retrieval_queries,
    load_cases,
    load_corpus,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "eval_corpus" / "course_notes"
SPEC_PATH = FIXTURE_DIR / "corpus.json"


def test_shipped_corpus_loads_with_all_four_kinds() -> None:
    corpus, cases = load_corpus(SPEC_PATH)

    assert corpus.name == "course_notes"
    assert len(corpus.documents) == 5
    assert len(cases) == 30
    assert {case.kind for case in cases} == {"term", "structure", "paraphrase", "unanswerable"}
    assert len({case.id for case in cases}) == 30


def test_unanswerable_cases_declare_no_expectations() -> None:
    _corpus, cases = load_corpus(SPEC_PATH)

    unanswerable = [case for case in cases if case.kind == "unanswerable"]
    assert unanswerable
    for case in unanswerable:
        assert case.expected_section_paths == []
        assert case.expected_keywords == []


def test_paraphrase_cases_expose_variants() -> None:
    _corpus, cases = load_corpus(SPEC_PATH)

    paraphrase = next(case for case in cases if case.kind == "paraphrase")
    queries = case_retrieval_queries(paraphrase)
    assert queries[0] == paraphrase.question
    assert queries[1:] == paraphrase.variants
    assert len(queries) >= 2


def test_answerable_cases_point_at_manifest_titles() -> None:
    corpus, cases = load_corpus(SPEC_PATH)

    titles = {document.title for document in corpus.documents}
    expected_roots = {
        path.split(" / ", 1)[0] for case in cases for path in case.expected_section_paths
    }
    assert expected_roots <= titles


def _write_spec(tmp_path: Path, manifest: dict, cases: list[dict]) -> Path:
    (tmp_path / "doc.md").write_text("# 标题\n\n正文内容。\n", encoding="utf-8")
    spec_path = tmp_path / "corpus.json"
    spec_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    cases_path = tmp_path / manifest.get("cases_file", "cases.jsonl")
    cases_path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases),
        encoding="utf-8",
    )
    return spec_path


def _manifest() -> dict:
    return {
        "name": "tiny",
        "documents": [{"path": "doc.md", "title": "讲义"}],
        "cases_file": "cases.jsonl",
    }


def test_load_cases_reports_line_number_for_broken_json(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        '{"id": "a", "kind": "term", "question": "q", "expected_keywords": ["x"]}\n'
        '{"id": "b", "kind": "term", "question": \n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"cases\.jsonl:2: invalid JSON"):
        load_cases(cases_path)


def test_load_cases_rejects_unanswerable_with_expectations(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "id": "u",
                "kind": "unanswerable",
                "question": "q",
                "expected_keywords": ["x"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not declare expectations"):
        load_cases(cases_path)


def test_load_cases_rejects_answerable_case_without_expectations(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps({"id": "a", "kind": "term", "question": "q"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="needs expected_section_paths or expected_keywords"):
        load_cases(cases_path)


def test_load_cases_rejects_empty_file(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no golden cases"):
        load_cases(cases_path)


def test_load_corpus_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    case = {"id": "dup", "kind": "term", "question": "q", "expected_keywords": ["x"]}
    spec_path = _write_spec(tmp_path, _manifest(), [case, case])

    with pytest.raises(ValueError, match="duplicate case id"):
        load_corpus(spec_path)


def test_load_corpus_rejects_unknown_section_root(tmp_path: Path) -> None:
    case = {
        "id": "a",
        "kind": "term",
        "question": "q",
        "expected_section_paths": ["别的文档 / 第1章 / 1.1 节"],
    }
    spec_path = _write_spec(tmp_path, _manifest(), [case])

    with pytest.raises(ValueError, match="unknown document title"):
        load_corpus(spec_path)


def test_load_corpus_rejects_missing_document(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["documents"] = [{"path": "missing.md", "title": "讲义"}]
    case = {"id": "a", "kind": "term", "question": "q", "expected_keywords": ["x"]}
    spec_path = _write_spec(tmp_path, manifest, [case])

    with pytest.raises(ValueError, match="document not found"):
        load_corpus(spec_path)


def test_load_corpus_rejects_missing_cases_file(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("正文", encoding="utf-8")
    spec_path = tmp_path / "corpus.json"
    spec_path.write_text(json.dumps(_manifest(), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="cases file not found"):
        load_corpus(spec_path)


def test_keywords_only_case_is_valid() -> None:
    case = EvalCase(
        id="kw",
        kind="term",
        question="q",
        expected_keywords=["关键词"],
    )

    assert case.expected_section_paths == []
    assert case_retrieval_queries(case) == ["q"]
