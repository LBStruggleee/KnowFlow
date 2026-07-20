import json
import logging

from app.core.database import get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.knowledge_base import KnowledgeBase
from app.schemas.conversation import (
    ChatMessageRead,
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> Conversation:
    if db.get(KnowledgeBase, payload.kb_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    conversation = Conversation(kb_id=payload.kb_id, title=payload.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    kb_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[Conversation]:
    statement = select(Conversation).order_by(Conversation.updated_at.desc())
    if kb_id is not None:
        statement = statement.where(Conversation.kb_id == kb_id)
    return list(db.scalars(statement))


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.asc())
        )
    )
    return ConversationDetail(
        id=conversation.id,
        kb_id=conversation.kb_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ChatMessageRead(
                id=message.id,
                conversation_id=message.conversation_id,
                kb_id=message.kb_id,
                role=message.role,
                content=message.content,
                sources=_load_sources(message.sources_json),
                prompt_tokens=message.prompt_tokens,
                completion_tokens=message.completion_tokens,
                total_tokens=message.total_tokens,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).delete()
    db.delete(conversation)
    db.commit()


def _load_sources(value: str) -> list[dict[str, object]]:
    try:
        sources = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed message sources JSON")
        return []
    return sources if isinstance(sources, list) else []
