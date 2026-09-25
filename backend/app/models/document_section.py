from datetime import datetime

from app.core.database import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class DocumentSection(Base):
    __tablename__ = "document_section"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_section.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    section_path: Mapped[str] = mapped_column(Text, default="")
    section_level: Mapped[int] = mapped_column(Integer, default=0)
    section_order: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
