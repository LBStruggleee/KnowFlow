from typing import Any

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services.startup_recovery import reconcile_orphan_vectors
from sqlalchemy.orm import Session


class _FakeCollection:
    def __init__(self, name: str, vector_ids: list[str]) -> None:
        self.name = name
        self.ids = list(vector_ids)
        self.deleted: list[str] = []
        self.fail_on_get = False

    def get(self, include: Any = None, limit: int = 500, offset: int = 0) -> dict[str, Any]:
        if self.fail_on_get:
            raise RuntimeError("collection unreachable")
        return {"ids": self.ids[offset : offset + limit]}

    def delete(self, ids: list[str]) -> None:
        self.deleted.extend(ids)
        for vector_id in ids:
            self.ids.remove(vector_id)


def _seed_chunks(db_session: Session, count: int) -> None:
    kb = KnowledgeBase(name="ReconcileKB")
    db_session.add(kb)
    db_session.flush()
    document = Document(
        kb_id=kb.id,
        title="doc",
        file_name="doc.md",
        file_path="storage/uploads/1/doc.md",
        file_type="md",
    )
    db_session.add(document)
    db_session.flush()
    for index in range(count):
        db_session.add(
            DocumentChunk(
                kb_id=kb.id,
                document_id=document.id,
                chunk_index=index,
                content="正文",
                token_count=2,
            )
        )
    db_session.commit()


def test_reconcile_deletes_vectors_missing_from_sqlite(db_session: Session, monkeypatch) -> None:
    _seed_chunks(db_session, count=2)
    primary = _FakeCollection("primary", ["chunk-1", "chunk-2", "chunk-9", "legacy-entry"])
    fallback = _FakeCollection("fallback", ["chunk-2", "chunk-404"])
    monkeypatch.setattr(
        "app.services.startup_recovery.vector_store_service.known_collections",
        lambda: [primary, fallback],
    )

    removed = reconcile_orphan_vectors(db_session)

    assert removed == 3
    assert primary.deleted == ["chunk-9", "legacy-entry"]
    assert fallback.deleted == ["chunk-404"]
    assert primary.ids == ["chunk-1", "chunk-2"]
    assert fallback.ids == ["chunk-2"]


def test_reconcile_keeps_vectors_backed_by_live_chunks(db_session: Session, monkeypatch) -> None:
    _seed_chunks(db_session, count=2)
    primary = _FakeCollection("primary", ["chunk-1", "chunk-2"])
    monkeypatch.setattr(
        "app.services.startup_recovery.vector_store_service.known_collections",
        lambda: [primary],
    )

    removed = reconcile_orphan_vectors(db_session)

    assert removed == 0
    assert primary.deleted == []
    assert primary.ids == ["chunk-1", "chunk-2"]


def test_reconcile_survives_a_failing_collection(db_session: Session, monkeypatch) -> None:
    _seed_chunks(db_session, count=1)
    broken = _FakeCollection("broken", ["chunk-77"])
    broken.fail_on_get = True
    healthy = _FakeCollection("healthy", ["chunk-1", "chunk-8"])
    monkeypatch.setattr(
        "app.services.startup_recovery.vector_store_service.known_collections",
        lambda: [broken, healthy],
    )

    removed = reconcile_orphan_vectors(db_session)

    assert removed == 1
    assert healthy.deleted == ["chunk-8"]
