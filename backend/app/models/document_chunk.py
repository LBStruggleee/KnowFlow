from datetime import datetime

from app.core.database import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_base.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_section.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    search_text: Mapped[str] = mapped_column(Text, default="")
    # Result of the ingestion-time injection screen. ``injection_rules`` keeps
    # the matched rule names so a downgraded chunk can be explained later. The
    # server defaults keep raw inserts from pre-injection code paths valid.
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    injection_rules: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
