import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "eval_retrieval.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("eval_retrieval_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script_module()


def test_parse_args_rejects_unknown_channel() -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["--channels", "hybrid,rerank"])


def test_parse_args_rejects_non_positive_k() -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["--k", "0"])


def test_smoke_subset_picks_one_case_per_kind() -> None:
    from app.services.eval.corpus import load_corpus

    _corpus, cases = load_corpus(script.DEFAULT_CORPUS)

    picked = script._smoke_subset(cases)

    assert [case.kind for case in picked] == ["term", "structure", "paraphrase", "unanswerable"]


def test_aggregate_computes_metrics_and_refusal() -> None:
    outcomes = {
        "hit": script.CaseOutcome(
            case_id="hit", kind="term", relevant_ids=[1], hits=[1, 2], gate_score=0.9
        ),
        "miss": script.CaseOutcome(
            case_id="miss", kind="term", relevant_ids=[3], hits=[4], gate_score=0.7
        ),
        "no_answer": script.CaseOutcome(
            case_id="no_answer", kind="unanswerable", relevant_ids=[], hits=[5], gate_score=0.1
        ),
    }

    aggregate = script._aggregate(outcomes, [1, 5])

    assert aggregate["answerable_cases"] == 2
    assert aggregate["metrics"]["recall@1"] == pytest.approx(0.5)
    assert aggregate["metrics"]["mrr"] == pytest.approx(0.5)
    assert aggregate["refusal_accuracy"]["0.5"] == pytest.approx(1.0)


def test_render_markdown_contains_all_sections() -> None:
    report = {
        "generated_at": "2026-11-02T00:00:00+00:00",
        "corpus": {"name": "tiny", "documents": ["讲义"], "cases": 1, "smoke": False},
        "config": {
            "channels": ["hybrid"],
            "k_values": [5],
            "placebo": True,
            "flat_pdf": False,
            "chunk_size": 800,
            "chunk_overlap": 150,
            "embedding": {
                "embedding_provider": "hashing_v1",
                "embedding_mode": "hashing",
                "embedding_degraded": True,
            },
        },
        "relevance": {"answerable_cases": 1, "resolved_cases": 1, "unresolved_cases": []},
        "channels": {
            "hybrid": {
                "answerable_cases": 1,
                "metrics": {"recall@5": 1.0, "ndcg@5": 1.0, "hit_rate@5": 1.0, "mrr": 1.0},
                "refusal_accuracy": {"0.0": 1.0, "0.3": 1.0, "0.5": 1.0, "0.7": 1.0},
            }
        },
        "variant_consistency": {"hybrid": 1.0},
        "placebo": {
            "hybrid": {
                "real": {
                    "answerable_cases": 1,
                    "metrics": {"recall@5": 1.0, "ndcg@10": 1.0, "mrr": 1.0},
                },
                "shuffled": {
                    "answerable_cases": 1,
                    "metrics": {"recall@5": 0.5, "ndcg@10": 0.5, "mrr": 0.5},
                },
            }
        },
    }

    markdown = script._render_markdown(report)

    assert "检索评测基线报告" in markdown
    assert "通道对比" in markdown
    assert "安慰剂对照" in markdown
    assert "同义改写一致性" in markdown
    assert "拒答准确率" in markdown
    assert "+0.500" in markdown


def test_cli_smoke_run_is_isolated_and_writes_report(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    argv = [sys.executable, str(SCRIPT_PATH), "--smoke", "--output", str(output)]
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        # Windows occasionally refuses to reopen a freshly created temp Chroma
        # directory (antivirus or the search indexer holding a handle). One
        # retry absorbs that environment flake without hiding a real failure:
        # the second attempt still has to produce the report.
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    report = output.read_text(encoding="utf-8")
    assert "检索评测基线报告" in report
    # The harness must force the offline hashing provider, never a cloud key.
    assert "hashing" in report
    assert "smoke 子集" in report
