"""Golden-question corpus for the offline retrieval evaluation harness.

The corpus is described by a small ``corpus.json`` manifest next to the
documents. Golden cases live in a JSONL file: one JSON object per line, so a
diff of the question set stays readable and a single broken line can be
reported with its line number.

Design rules that the loader enforces, because a silently malformed golden set
produces flattering numbers instead of useful ones:

* ``unanswerable`` cases must not declare expectations;
* every answerable case must declare at least one expectation;
* case ids are unique;
* each expected section path starts with a document title from the manifest,
  which catches typos instead of letting them score zero forever.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

EvalKind = Literal["term", "structure", "paraphrase", "unanswerable"]
SECTION_PATH_SEPARATOR = " / "


class EvalCase(BaseModel):
    """One golden question and the section paths that answer it."""

    id: str
    kind: EvalKind
    question: str
    expected_section_paths: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def _check_expectations(self) -> "EvalCase":
        if self.kind == "unanswerable":
            if self.expected_section_paths or self.expected_keywords:
                raise ValueError("unanswerable case must not declare expectations")
            return self
        if not self.expected_section_paths and not self.expected_keywords:
            raise ValueError("answerable case needs expected_section_paths or expected_keywords")
        return self


class CorpusDocument(BaseModel):
    path: str
    title: str


class EvalCorpus(BaseModel):
    name: str
    documents: list[CorpusDocument]
    cases_file: str = "cases.jsonl"
    description: str = ""


def load_cases(path: Path) -> list[EvalCase]:
    """Parse a JSONL golden set, reporting the offending line on failure."""
    cases: list[EvalCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON ({exc.msg})") from exc
        try:
            cases.append(EvalCase.model_validate(payload))
        except ValidationError as exc:
            first_error = exc.errors()[0]
            location = ".".join(str(part) for part in first_error["loc"]) or "<root>"
            raise ValueError(
                f"{path.name}:{line_number}: invalid case at {location}: {first_error['msg']}"
            ) from exc
    if not cases:
        raise ValueError(f"{path.name}: no golden cases found")
    return cases


def load_corpus(spec_path: Path) -> tuple[EvalCorpus, list[EvalCase]]:
    """Load and validate a manifest plus its golden cases.

    Document paths are resolved relative to the manifest directory so a corpus
    folder stays relocatable.
    """
    try:
        corpus = EvalCorpus.model_validate_json(spec_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError(f"{spec_path.name}: invalid corpus manifest: {exc}") from exc

    cases_path = spec_path.parent / corpus.cases_file
    if not cases_path.is_file():
        raise ValueError(f"{spec_path.name}: cases file not found: {corpus.cases_file}")
    cases = load_cases(cases_path)
    _validate_documents(spec_path, corpus)
    _validate_cases(corpus, cases)
    return corpus, cases


def _validate_documents(spec_path: Path, corpus: EvalCorpus) -> None:
    titles: set[str] = set()
    for document in corpus.documents:
        if document.title in titles:
            raise ValueError(f"{spec_path.name}: duplicate document title: {document.title}")
        titles.add(document.title)
        if not (spec_path.parent / document.path).is_file():
            raise ValueError(f"{spec_path.name}: document not found: {document.path}")


def _validate_cases(corpus: EvalCorpus, cases: list[EvalCase]) -> None:
    titles = {document.title for document in corpus.documents}
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"{corpus.name}: duplicate case id: {case.id}")
        seen.add(case.id)
        for path in case.expected_section_paths:
            root = path.split(SECTION_PATH_SEPARATOR, 1)[0]
            if root not in titles:
                raise ValueError(
                    f"{corpus.name}: case {case.id} references unknown document title: {root}"
                )


def case_retrieval_queries(case: EvalCase) -> list[str]:
    """All query wordings for a case, primary question first."""
    return [case.question, *case.variants]
