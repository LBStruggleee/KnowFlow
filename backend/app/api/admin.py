import json
import logging
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

from app.core.database import get_db
from app.core.db_utils import load_json_column, safe_commit
from app.core.files import UPLOAD_ROOT, safe_unlink
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.models.learning_record import LearningRecord
from app.models.system_setting import SystemSetting
from app.schemas.admin import (
    DataClearRead,
    ProviderStatusRead,
    SystemSettingsRead,
    SystemSettingsUpdate,
    SystemStatusRead,
    TokenUsageRead,
)
from app.services.llm_service import llm_service
from app.services.settings_service import (
    GlassVariant,
    PrivacyMode,
    RetrievalChannel,
    typed_settings,
    update_settings,
)
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)

# Rows serialized per streamed batch; bounds peak memory for the export
# regardless of table size.
EXPORT_BATCH_ROWS = 200


@router.get("/settings", response_model=SystemSettingsRead)
def get_system_settings(db: Session = Depends(get_db)) -> SystemSettingsRead:
    return SystemSettingsRead(**typed_settings(db))


@router.patch("/settings", response_model=SystemSettingsRead)
def patch_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    values = update_settings(db, payload.model_dump(exclude_unset=True))
    # update_settings seeds every key with a valid default and normalizes
    # retrieval_channels, so the literal narrowing below cannot fail.
    return SystemSettingsRead(
        top_k=int(values["top_k"]),
        score_threshold=float(values["score_threshold"]),
        qwen_model=values["qwen_model"],
        temperature=float(values["temperature"]),
        privacy_mode=cast(PrivacyMode, values["privacy_mode"]),
        glass_variant=cast(GlassVariant, values["glass_variant"]),
        retrieval_channels=cast(RetrievalChannel, values["retrieval_channels"]),
    )


@router.get("/providers", response_model=ProviderStatusRead)
def get_provider_status(db: Session = Depends(get_db)) -> ProviderStatusRead:
    config = typed_settings(db)
    return ProviderStatusRead(
        llm_provider=str(config["qwen_model"]),
        llm_available=llm_service.available,
        embedding_provider=vector_store_service.embedding_provider,
        vector_collection=vector_store_service.collection_name,
        privacy_mode=config["privacy_mode"],
    )


@router.get("/status", response_model=SystemStatusRead)
def get_system_status(db: Session = Depends(get_db)) -> SystemStatusRead:
    token_usage = db.query(
        func.coalesce(func.sum(ChatMessage.prompt_tokens), 0),
        func.coalesce(func.sum(ChatMessage.completion_tokens), 0),
        func.coalesce(func.sum(ChatMessage.total_tokens), 0),
    ).one()
    return SystemStatusRead(
        knowledge_bases=db.query(KnowledgeBase).count(),
        documents=db.query(Document).count(),
        chunks=db.query(DocumentChunk).count(),
        conversations=db.query(Conversation).count(),
        messages=db.query(ChatMessage).count(),
        finished_documents=db.query(Document).filter(Document.status == "finished").count(),
        failed_documents=db.query(Document).filter(Document.status == "failed").count(),
        token_usage=TokenUsageRead(
            prompt_tokens=int(token_usage[0] or 0),
            completion_tokens=int(token_usage[1] or 0),
            total_tokens=int(token_usage[2] or 0),
        ),
    )


@router.get("/export")
def export_all_data(db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream the full export as a single JSON object.

    Rows are fetched with ``yield_per`` and serialized in batches, then
    released from the session, so the payload never materializes in memory
    and the response body has no size ceiling. The JSON shape (keys, row
    fields, ordering) is identical to the pre-streaming export.
    """
    return StreamingResponse(
        _export_stream(db),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="knowflow-export.json"'},
    )


def _export_stream(db: Session) -> Iterator[str]:
    yield '{"version":1,"knowledge_bases":'
    yield from _stream_rows(db, select(KnowledgeBase), _encode_model)
    yield ',"documents":'
    yield from _stream_rows(db, select(Document), _encode_document)
    yield ',"chunks":'
    yield from _stream_rows(db, select(DocumentChunk), _encode_model)
    yield ',"conversations":'
    yield from _stream_rows(db, select(Conversation), _encode_model)
    yield ',"messages":'
    yield from _stream_rows(db, select(ChatMessage), _encode_message)
    yield ',"learning_records":'
    yield from _stream_rows(db, select(LearningRecord), _encode_learning_record)
    yield ',"settings":'
    yield from _stream_settings_object(db)
    yield "}"


def _stream_rows(
    db: Session,
    statement: Any,
    encode: Callable[[Any], dict[str, Any]],
) -> Iterator[str]:
    """Yield a JSON array as batch-sized fragments while releasing each row."""
    emitted = False
    batch: list[str] = []
    for row in db.scalars(statement).yield_per(EXPORT_BATCH_ROWS):
        batch.append(json.dumps(encode(row), ensure_ascii=False, separators=(",", ":")))
        db.expunge(row)
        if len(batch) >= EXPORT_BATCH_ROWS:
            yield ("[" if not emitted else ",") + ",".join(batch)
            emitted = True
            batch.clear()
    if batch:
        yield ("[" if not emitted else ",") + ",".join(batch)
    elif not emitted:
        yield "["
    yield "]"


def _stream_settings_object(db: Session) -> Iterator[str]:
    batch: list[str] = []
    for item in db.scalars(select(SystemSetting)).yield_per(EXPORT_BATCH_ROWS):
        batch.append(
            json.dumps(item.key, ensure_ascii=False)
            + ":"
            + json.dumps(item.value, ensure_ascii=False)
        )
        db.expunge(item)
    yield "{" + ",".join(batch) + "}"


def _encode_model(model: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    return jsonable_encoder(_model_dict(model, exclude))


def _encode_document(model: Any) -> dict[str, Any]:
    return _encode_model(model, exclude={"file_path"})


def _encode_message(model: Any) -> dict[str, Any]:
    payload = _model_dict(model, exclude={"sources_json"})
    payload["sources"] = load_json_column(model.sources_json, [])
    return jsonable_encoder(payload)


def _encode_learning_record(model: Any) -> dict[str, Any]:
    payload = _model_dict(model, exclude={"tags_json", "metadata_json"})
    payload["tags"] = load_json_column(model.tags_json, [])
    payload["metadata"] = load_json_column(model.metadata_json, {})
    return jsonable_encoder(payload)


@router.delete("/data", response_model=DataClearRead)
def clear_all_data(
    confirmation: str = Query(...),
    db: Session = Depends(get_db),
) -> DataClearRead:
    if confirmation != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm data clearing.")

    kb_ids = list(db.scalars(select(KnowledgeBase.id)))
    file_paths = [Path(path) for path in db.scalars(select(Document.file_path))]
    counts = DataClearRead(
        knowledge_bases=len(kb_ids),
        documents=db.query(Document).count(),
        conversations=db.query(Conversation).count(),
        learning_records=db.query(LearningRecord).count(),
    )
    db.query(LearningRecord).delete()
    db.query(ChatMessage).delete()
    db.query(Conversation).delete()
    db.query(DocumentChunk).delete()
    db.query(Document).delete()
    db.query(KnowledgeBase).delete()
    safe_commit(db)

    for kb_id in kb_ids:
        try:
            vector_store_service.delete_knowledge_base(kb_id)
        except Exception:
            logger.exception("Vector cleanup failed for knowledge base id=%s during clear", kb_id)
    for file_path in file_paths:
        safe_unlink(file_path)
    for kb_id in kb_ids:
        upload_dir = (UPLOAD_ROOT / str(kb_id)).resolve()
        try:
            upload_dir.relative_to(UPLOAD_ROOT.resolve())
        except ValueError:
            continue
        if upload_dir.is_dir():
            shutil.rmtree(upload_dir, ignore_errors=True)
    return counts


def _model_dict(model: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    omitted = {"_sa_instance_state", *(exclude or set())}
    return {key: value for key, value in model.__dict__.items() if key not in omitted}
