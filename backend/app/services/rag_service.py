from typing import Any

from app.services.llm_service import llm_service
from app.services.vector_store_service import vector_store_service

SYSTEM_PROMPT = """你是 KnowFlow（知汇）中的大数据课程学习助手。
请严格基于给定参考资料回答用户问题。
如果参考资料中没有足够信息，请明确说明“知识库中未找到足够依据”。
回答要适合大数据专业学生理解，尽量分点说明。
不要编造不存在的文档、链接或来源。"""


class RagService:
    def answer(
        self,
        kb_id: int,
        question: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        sources = vector_store_service.search(kb_id=kb_id, query=question, top_k=top_k)
        retrieval_trace = _build_retrieval_trace(sources, score_threshold)
        if not sources:
            return {
                "answer": "知识库中未找到足够依据。",
                "sources": [],
                "usage": None,
                "retrieval_trace": retrieval_trace,
            }

        best_score = max(source["score"] for source in sources)
        if score_threshold > 0 and best_score < score_threshold:
            return {
                "answer": "知识库中未找到足够依据。",
                "sources": sources,
                "usage": None,
                "retrieval_trace": retrieval_trace,
            }

        context = _build_context(sources)
        user_prompt = f"""参考资料：
{context}

用户问题：
{question}"""

        result = llm_service.chat(
            SYSTEM_PROMPT,
            user_prompt,
            model=model,
            temperature=temperature,
        )
        return {
            "answer": result["content"],
            "sources": sources,
            "usage": result["usage"],
            "retrieval_trace": retrieval_trace,
        }


def _build_context(sources: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[资料 {index}]",
                    f"chunk_id: {source['chunk_id']}",
                    f"document_id: {source['document_id']}",
                    f"chunk_index: {source['chunk_index']}",
                    f"score: {source['score']:.4f}",
                    "content:",
                    source["content"],
                ]
            )
        )
    return "\n\n".join(blocks)


def _build_retrieval_trace(
    sources: list[dict[str, Any]],
    score_threshold: float,
) -> dict[str, Any]:
    best_score = max((source["score"] for source in sources), default=0.0)
    return {
        "top_k": len(sources),
        "score_threshold": score_threshold,
        "best_score": best_score,
        "passed_threshold": score_threshold <= 0 or best_score >= score_threshold,
        "matches": sources,
    }


rag_service = RagService()
