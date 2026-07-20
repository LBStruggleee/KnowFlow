import json

from app.core.config import settings
from app.core.database import get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.knowledge_base import KnowledgeBase
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import rag_service
from app.services.settings_service import typed_settings
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    knowledge_base = db.get(KnowledgeBase, payload.kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    config = typed_settings(db)
    top_k = payload.top_k if payload.top_k is not None else int(config["top_k"])

    conversation = _get_or_create_conversation(db, payload)
    history_messages = _load_history(db, conversation.id)

    try:
        result = rag_service.answer(
            kb_id=payload.kb_id,
            question=payload.question,
            top_k=top_k,
            score_threshold=float(config["score_threshold"]),
            model=str(config["qwen_model"]),
            temperature=float(config["temperature"]),
            history=history_messages,
        )
    except Exception:
        db.rollback()
        raise
    usage = result.get("usage") or {}

    user_message = ChatMessage(
        conversation_id=conversation.id,
        kb_id=payload.kb_id,
        role="user",
        content=payload.question,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        kb_id=payload.kb_id,
        role="assistant",
        content=result["answer"],
        sources_json=json.dumps(result.get("sources", []), ensure_ascii=False),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
    )
    conversation.updated_at = func.now()
    db.add_all([user_message, assistant_message])
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    result["conversation_id"] = conversation.id
    return ChatResponse(**result)


def _load_history(db: Session, conversation_id: int) -> list[dict[str, str]]:
    history = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.desc())
            .limit(settings.history_max_messages)
        )
    )
    selected: list[dict[str, str]] = []
    used_chars = 0
    for message in history:
        remaining = settings.history_max_chars - used_chars
        if remaining <= 0:
            break
        content = message.content[-remaining:]
        selected.append({"role": message.role, "content": content})
        used_chars += len(content)
    return list(reversed(selected))


def _get_or_create_conversation(db: Session, payload: ChatRequest) -> Conversation:
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None or conversation.kb_id != payload.kb_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
        return conversation

    title = payload.question.strip()[:40] or "新会话"
    conversation = Conversation(kb_id=payload.kb_id, title=title)
    db.add(conversation)
    db.flush()
    return conversation
