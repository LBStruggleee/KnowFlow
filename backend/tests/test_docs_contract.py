from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_product_and_technical_documents_define_the_v1_contract() -> None:
    product = (ROOT / "docs" / "产品设计改进方案.md").read_text(encoding="utf-8")
    technical = (ROOT / "docs" / "技术方案.md").read_text(encoding="utf-8")

    for capability in ["课程知识库", "学习助手", "学习记录", "设置", "本地抽取式回答"]:
        assert capability in product

    for endpoint in [
        "/api/chat",
        "/api/learning-records",
        "/api/admin/providers",
        "/api/admin/export",
        "/api/admin/data",
    ]:
        assert endpoint in technical

    assert "V1 验收" in technical
    assert "明确不在 V1" in product


def test_app_copy_keeps_generic_knowledge_base_positioning() -> None:
    from app.main import app
    from app.services.rag_service import NO_EVIDENCE_ANSWER, SYSTEM_PROMPT

    assert "大数据" not in app.description
    assert "大数据课程学习" not in SYSTEM_PROMPT
    assert "课程" not in NO_EVIDENCE_ANSWER

    # Guardrails required by the security posture must stay.
    assert "严格基于给定参考资料" in SYSTEM_PROMPT
    assert "不可信" in SYSTEM_PROMPT
    assert "知识库中未找到足够依据" in SYSTEM_PROMPT


def test_search_router_is_labeled_hybrid_search() -> None:
    from app.api.vector_search import router

    assert router.tags == ["hybrid search"]
