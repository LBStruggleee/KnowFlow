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
