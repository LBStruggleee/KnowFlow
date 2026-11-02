"""Offline retrieval evaluation harness.

Runs the real ingestion + hybrid search pipeline against a golden question set
inside an isolated temporary workspace, so an evaluation run never touches the
user's database or Chroma index:

* SQLite lives in a temp file (``DATABASE_URL``),
* Chroma lives in a temp directory (``KNOWFLOW_CHROMA_DIR``),
* embeddings are forced to the local hashing provider (offline, deterministic).

Two comparisons are produced:

* **channels** — vector / lexical / hybrid at the same top-k;
* **placebo** — the index is rebuilt with shuffled section titles (the paper's
  placebo control), so the delta measures how much the real heading-path
  tokens contribute. KnowFlow embeds chunk content only, so the vector channel
  is structurally invariant to this placebo; the report says so explicitly
  instead of implying a structural effect that was never measured.

Usage::

    python scripts/eval_retrieval.py --smoke
    python scripts/eval_retrieval.py --channels hybrid,vector,lexical --output report.md
"""

import argparse
import json
import os
import random
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CORPUS = BACKEND_DIR / "tests" / "fixtures" / "eval_corpus" / "course_notes" / "corpus.json"
PLACEBO_SHUFFLE_SEED = 20261102
REFUSAL_THRESHOLDS = (0.0, 0.3, 0.5, 0.7)
K_VALUES = (1, 3, 5, 10)


@dataclass
class CaseOutcome:
    case_id: str
    kind: str
    relevant_ids: list[int]
    hits: list[int]
    gate_score: float


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KnowFlow offline retrieval evaluation")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="corpus.json manifest path")
    parser.add_argument("--channels", default="hybrid,vector,lexical")
    parser.add_argument("--k", type=int, default=10, help="maximum top-k to request")
    parser.add_argument("--no-placebo", action="store_true", help="skip the shuffled-path run")
    parser.add_argument("--smoke", action="store_true", help="tiny case subset, no placebo")
    parser.add_argument("--output", help="write the Markdown report to this path")
    parser.add_argument("--json", dest="json_path", help="write raw metrics JSON to this path")
    parser.add_argument("--keep-workspace", action="store_true", help="keep the temp workspace")
    parser.add_argument("--workspace", help="run in this directory instead of a temp one")
    args = parser.parse_args(argv)
    args.channels = [channel.strip() for channel in args.channels.split(",") if channel.strip()]
    if not args.channels:
        parser.error("--channels must list at least one channel")
    if not set(args.channels) <= {"hybrid", "vector", "lexical"}:
        parser.error("--channels accepts only hybrid, vector, lexical")
    if args.k <= 0:
        parser.error("--k must be greater than 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = (
        Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix="kf-eval-"))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    _bootstrap_env(workspace)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from app.services.eval.corpus import load_corpus

    manifest_path = Path(args.corpus).resolve()
    corpus, cases = load_corpus(manifest_path)
    if args.smoke:
        cases = _smoke_subset(cases)

    kb_id = _build_index(corpus, manifest_path.parent)
    # Relevance is resolved exactly once, before the placebo rebuild: otherwise
    # the shuffled titles would silently change the ground truth and make the
    # placebo delta meaningless.
    relevance = _resolve_all_relevant(kb_id, cases)
    real_outcomes, variant_hits = _run_channels(
        kb_id, cases, args.channels, k=args.k, relevance=relevance
    )

    placebo_outcomes: dict[str, dict[str, CaseOutcome]] = {}
    if not args.no_placebo and not args.smoke:
        _apply_placebo()
        for channel in args.channels:
            placebo_outcomes[channel] = _run_single_channel(
                kb_id, cases, channel, k=args.k, relevance=relevance
            )

    k_values = [k for k in K_VALUES if k <= args.k]
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus": {
            "name": corpus.name,
            "documents": [document.title for document in corpus.documents],
            "cases": len(cases),
            "smoke": args.smoke,
        },
        "config": _config_payload(args, k_values),
        "relevance": _relevance_summary(cases, relevance),
        "channels": {
            channel: _aggregate(outcomes, k_values) for channel, outcomes in real_outcomes.items()
        },
        "variant_consistency": {
            channel: _variant_consistency(real_outcomes[channel], hits, k=min(5, args.k))
            for channel, hits in variant_hits.items()
        },
        "placebo": {
            channel: {
                "real": _aggregate(real_outcomes[channel], k_values),
                "shuffled": _aggregate(outcomes, k_values),
            }
            for channel, outcomes in placebo_outcomes.items()
        },
    }

    markdown = _render_markdown(report)
    print(markdown)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"\n[report] {args.output}")
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[json] {args.json_path}")

    if not args.keep_workspace and not args.workspace:
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)
    return 0


def _bootstrap_env(workspace: Path) -> None:
    """Point every stateful dependency at the throwaway workspace.

    Must run before any ``app`` import: the database engine and the Chroma
    client are constructed at module import time.
    """
    os.environ["DATABASE_URL"] = f"sqlite:///{workspace / 'eval.db'}"
    os.environ["KNOWFLOW_CHROMA_DIR"] = str(workspace / "chroma")
    os.environ["EMBEDDING_PROVIDER"] = "hashing"
    os.environ["DASHSCOPE_API_KEY"] = ""


def _smoke_subset(cases: list) -> list:
    picked = []
    for kind in ("term", "structure", "paraphrase", "unanswerable"):
        picked.extend([case for case in cases if case.kind == kind][:1])
    return picked


def _build_index(corpus, corpus_dir: Path) -> int:
    from app.core.database import Base, SessionLocal, engine
    from app.core.migrations import run_migrations
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    from app.services.document_processing_service import process_document_record

    Base.metadata.create_all(engine)
    run_migrations(engine)

    with SessionLocal() as db:
        knowledge_base = KnowledgeBase(name=f"eval-{corpus.name}", description="evaluation only")
        db.add(knowledge_base)
        db.flush()
        for spec_document in corpus.documents:
            source = (corpus_dir / spec_document.path).resolve()
            document = Document(
                kb_id=knowledge_base.id,
                title=spec_document.title,
                file_name=source.name,
                file_path=str(source),
                file_type=source.suffix.lower(),
                status="processing",
            )
            db.add(document)
            db.flush()
            process_document_record(db, document.id)
        db.commit()
        return knowledge_base.id


def _run_channels(
    kb_id: int,
    cases: list,
    channels: list[str],
    *,
    k: int,
    relevance: dict[str, set[int]],
) -> tuple[dict[str, dict[str, CaseOutcome]], dict[str, dict[str, list[list[int]]]]]:
    from app.core.database import SessionLocal
    from app.services.eval.corpus import case_retrieval_queries

    outcomes: dict[str, dict[str, CaseOutcome]] = {}
    variants: dict[str, dict[str, list[list[int]]]] = {}
    with SessionLocal() as db:
        for channel in channels:
            channel_outcomes = _run_single_channel(
                kb_id, cases, channel, k=k, relevance=relevance, db=db
            )
            outcomes[channel] = channel_outcomes
            variant_map: dict[str, list[list[int]]] = {}
            for case in cases:
                queries = case_retrieval_queries(case)
                if len(queries) < 2:
                    continue
                variant_map[case.id] = [
                    _retrieve(db, kb_id, query, channel, k=k)[0] for query in queries
                ]
            variants[channel] = variant_map
    return outcomes, variants


def _run_single_channel(
    kb_id: int,
    cases: list,
    channel: str,
    *,
    k: int,
    relevance: dict[str, set[int]],
    db=None,
) -> dict[str, CaseOutcome]:
    from app.core.database import SessionLocal

    if db is not None:
        return _collect_outcomes(db, kb_id, cases, channel, k, relevance)

    with SessionLocal() as session:
        return _collect_outcomes(session, kb_id, cases, channel, k, relevance)


def _collect_outcomes(
    db,
    kb_id: int,
    cases: list,
    channel: str,
    k: int,
    relevance: dict[str, set[int]],
) -> dict[str, CaseOutcome]:
    outcomes: dict[str, CaseOutcome] = {}
    for case in cases:
        hits, gate = _retrieve(db, kb_id, case.question, channel, k=k)
        outcomes[case.id] = CaseOutcome(
            case_id=case.id,
            kind=case.kind,
            relevant_ids=sorted(relevance.get(case.id, set())),
            hits=hits,
            gate_score=gate,
        )
    return outcomes


def _resolve_all_relevant(kb_id: int, cases: list) -> dict[str, set[int]]:
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        return {case.id: _resolve_relevant(db, kb_id, case) for case in cases}


def _retrieve(db, kb_id: int, query: str, channel: str, *, k: int) -> tuple[list[int], float]:
    from app.services.hybrid_search import search_hybrid, threshold_score

    result = search_hybrid(db, kb_id=kb_id, query=query, top_k=k, channels=channel)
    semantics = result.trace.get("score_semantics", "rrf_fused")
    hits = [int(hit["chunk_id"]) for hit in result.hits]
    return hits, threshold_score(result.hits, semantics)


def _resolve_relevant(db, kb_id: int, case) -> set[int]:
    from app.models.document_chunk import DocumentChunk
    from app.models.document_section import DocumentSection
    from sqlalchemy import select

    relevant: set[int] = set()
    if case.expected_section_paths:
        rows = db.scalars(
            select(DocumentChunk.id)
            .join(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
            .where(DocumentChunk.kb_id == kb_id)
            .where(DocumentSection.section_path.in_(case.expected_section_paths))
        )
        relevant.update(int(chunk_id) for chunk_id in rows)
    if not relevant:
        for keyword in case.expected_keywords:
            rows = db.scalars(
                select(DocumentChunk.id)
                .where(DocumentChunk.kb_id == kb_id)
                .where(DocumentChunk.content.contains(keyword))
            )
            relevant.update(int(chunk_id) for chunk_id in rows)
    return relevant


def _apply_placebo() -> None:
    """Replace real heading paths with shuffled titles and rebuild search_text.

    Relevance was resolved before this call, so chunk ids stay stable while the
    structural signal in the lexical index is destroyed (the placebo control).
    """
    from app.core.database import SessionLocal
    from app.models.document_chunk import DocumentChunk
    from app.models.document_section import DocumentSection
    from app.services.lexical_search import _build_search_text
    from sqlalchemy import select

    with SessionLocal() as db:
        sections = list(db.scalars(select(DocumentSection).order_by(DocumentSection.id)))
        titles = [section.title for section in sections if section.section_level > 0]
        random.Random(PLACEBO_SHUFFLE_SEED).shuffle(titles)
        new_paths: dict[int, str] = {}
        title_index = 0
        for section in sections:
            if section.section_level == 0:
                new_paths[section.id] = section.title
                continue
            section.title = titles[title_index]
            title_index += 1
            parent_path = new_paths.get(section.parent_section_id or -1, "")
            section.section_path = (
                f"{parent_path} / {section.title}" if parent_path else section.title
            )
            new_paths[section.id] = section.section_path
        for chunk in db.scalars(select(DocumentChunk)):
            path = new_paths.get(chunk.section_id or -1, "")
            chunk.search_text = _build_search_text(chunk.content, path)
        db.commit()


def _aggregate(outcomes: dict[str, CaseOutcome], k_values: list[int]) -> dict[str, Any]:
    """Average metrics over answerable cases plus refusal accuracy over all."""
    from app.services.eval.metrics import (
        hit_rate_at_k,
        ndcg_at_k,
        recall_at_k,
        reciprocal_rank,
    )

    answerable = [
        outcome
        for outcome in outcomes.values()
        if outcome.kind != "unanswerable" and outcome.relevant_ids
    ]
    metrics: dict[str, float] = {}
    for k in k_values:
        metrics[f"recall@{k}"] = _mean(
            recall_at_k(outcome.hits, set(outcome.relevant_ids), k) for outcome in answerable
        )
        metrics[f"ndcg@{k}"] = _mean(
            ndcg_at_k(outcome.hits, set(outcome.relevant_ids), k) for outcome in answerable
        )
        metrics[f"hit_rate@{k}"] = _mean(
            hit_rate_at_k(outcome.hits, set(outcome.relevant_ids), k) for outcome in answerable
        )
    metrics["mrr"] = _mean(
        reciprocal_rank(outcome.hits, set(outcome.relevant_ids)) for outcome in answerable
    )
    refusal = {
        f"{threshold:.1f}": _refusal_accuracy(outcomes.values(), threshold)
        for threshold in REFUSAL_THRESHOLDS
    }
    return {
        "answerable_cases": len(answerable),
        "metrics": {name: round(value, 4) for name, value in metrics.items()},
        "refusal_accuracy": {name: round(value, 4) for name, value in refusal.items()},
    }


def _refusal_accuracy(outcomes, threshold: float) -> float:
    from app.services.eval.metrics import refusal_accuracy

    expected: list[bool] = []
    predicted: list[bool] = []
    for outcome in outcomes:
        expected.append(outcome.kind != "unanswerable")
        predicted.append(outcome.gate_score >= threshold)
    return refusal_accuracy(expected, predicted)


def _variant_consistency(
    outcomes: dict[str, CaseOutcome],
    variant_hits: dict[str, list[list[int]]],
    *,
    k: int,
) -> float:
    from app.services.eval.metrics import variant_consistency_at_k

    per_case = []
    for case_id, hits_per_variant in variant_hits.items():
        outcome = outcomes.get(case_id)
        if outcome is None or not outcome.relevant_ids:
            continue
        per_case.append(variant_consistency_at_k(hits_per_variant, set(outcome.relevant_ids), k))
    return _mean(per_case)


def _mean(values) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _relevance_summary(cases: list, relevance: dict[str, set[int]]) -> dict[str, Any]:
    answerable = [case for case in cases if case.kind != "unanswerable"]
    unresolved = [case.id for case in answerable if not relevance.get(case.id)]
    return {
        "answerable_cases": len(answerable),
        "resolved_cases": len(answerable) - len(unresolved),
        "unresolved_cases": unresolved,
    }


def _config_payload(args: argparse.Namespace, k_values: list[int]) -> dict[str, Any]:
    from app.services.embedding_service import embedding_status
    from app.services.text_chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE

    return {
        "channels": args.channels,
        "k_values": k_values,
        "placebo": not args.no_placebo and not args.smoke,
        "chunk_size": DEFAULT_CHUNK_SIZE,
        "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
        "embedding": embedding_status(),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    config = report["config"]
    embedding = config["embedding"]
    smoke_suffix = "，smoke 子集" if report["corpus"]["smoke"] else ""
    lines = [
        "# 检索评测基线报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 语料：{report['corpus']['name']}（{len(report['corpus']['documents'])} 篇，"
        f"{report['corpus']['cases']} 条问题{smoke_suffix}）",
        f"- 分块：{config['chunk_size']} 字符 / 重叠 {config['chunk_overlap']}",
        f"- 向量通道：{embedding['embedding_provider']}（模式 {embedding['embedding_mode']}，"
        f"降级 {embedding['embedding_degraded']}）",
        f"- 通道：{', '.join(config['channels'])}；k 取值：{config['k_values']}",
        f"- 相关块解析：{report['relevance']['resolved_cases']}/"
        f"{report['relevance']['answerable_cases']} 条可回答问题命中标注",
        "",
    ]
    if report["relevance"]["unresolved_cases"]:
        lines.append(
            "> 警告：以下问题未能把标注解析成任何 chunk，相关指标按 0 计入："
            + ", ".join(report["relevance"]["unresolved_cases"])
        )
        lines.append("")

    k_values = config["k_values"]
    lines.append("## 通道对比（真实标题路径）")
    lines.append("")
    header = ["通道"]
    header.extend(f"Recall@{k}" for k in k_values)
    header.extend(f"nDCG@{k}" for k in k_values)
    header.extend(["MRR", f"Hit@{k_values[-1]}"])
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for channel, payload in report["channels"].items():
        metrics = payload["metrics"]
        row = [channel]
        row.extend(f"{metrics[f'recall@{k}']:.3f}" for k in k_values)
        row.extend(f"{metrics[f'ndcg@{k}']:.3f}" for k in k_values)
        row.append(f"{metrics['mrr']:.3f}")
        row.append(f"{metrics[f'hit_rate@{k_values[-1]}']:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    if report["placebo"]:
        lines.append("## 安慰剂对照（打乱标题路径）")
        lines.append("")
        lines.append(
            f"打乱方式：固定种子 {PLACEBO_SHUFFLE_SEED} 打乱全部小节标题并重建 `search_text`；"
            "向量通道只嵌入正文，对路径打乱不敏感，该项差异应接近 0。"
        )
        lines.append("")
        lines.append("| 通道 | 指标 | 真实路径 | 打乱路径 | 差值 |")
        lines.append("|---|---|---|---|---|")
        for channel, payload in report["placebo"].items():
            for name in ("recall@5", "ndcg@10", "mrr"):
                if name not in payload["real"]["metrics"]:
                    continue
                real_value = payload["real"]["metrics"][name]
                shuffled_value = payload["shuffled"]["metrics"][name]
                lines.append(
                    f"| {channel} | {name} | {real_value:.3f} | {shuffled_value:.3f} | "
                    f"{real_value - shuffled_value:+.3f} |"
                )
        lines.append("")

    if report["variant_consistency"]:
        lines.append("## 同义改写一致性（paraphrase 组）")
        lines.append("")
        lines.append("| 通道 | 改写后仍命中的比例 |")
        lines.append("|---|---|")
        for channel, value in report["variant_consistency"].items():
            lines.append(f"| {channel} | {value:.3f} |")
        lines.append("")

    lines.append("## 拒答准确率（按阈值）")
    lines.append("")
    thresholds = list(REFUSAL_THRESHOLDS)
    lines.append("| 通道 | " + " | ".join(f"阈值 {t:.1f}" for t in thresholds) + " |")
    lines.append("|" + "---|" * (len(thresholds) + 1))
    for channel, payload in report["channels"].items():
        refusal = payload["refusal_accuracy"]
        cells = " | ".join(f"{refusal[f'{t:.1f}']:.3f}" for t in thresholds)
        lines.append(f"| {channel} | {cells} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
