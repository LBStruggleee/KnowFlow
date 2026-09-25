import json
import shutil
from pathlib import Path
from typing import Any

from app.core.database import BASE_DIR, get_db
from app.core.db_utils import safe_commit
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
from app.services.settings_service import typed_settings, update_settings
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])
UPLOAD_ROOT = BASE_DIR / "storage" / "uploads"


@router.get("/settings", response_model=SystemSettingsRead)
def get_system_settings(db: Session = Depends(get_db)) -> SystemSettingsRead:
    return SystemSettingsRead(**typed_settings(db))


@router.patch("/settings", response_model=SystemSettingsRead)
def patch_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    values = update_settings(db, payload.model_dump(exclude_unset=True))
    return SystemSettingsRead(
        top_k=int(values["top_k"]),
        score_threshold=float(values["score_threshold"]),
        qwen_model=values["qwen_model"],
        temperature=float(values["temperature"]),
        privacy_mode=values["privacy_mode"],
        glass_variant=values["glass_variant"],
        retrieval_channels=values["retrieval_channels"],
    )


@router.get("/providers", response_model=ProviderStatusRead)
def get_provider_status(db: Session = Depends(get_db)) -> ProviderStatusRead:
    config = typed_settings(db)
    return ProviderStatusRead(
        llm_provider=str(config["qwen_model"]),
        llm_available=llm_service.available,
        embedding_provider=vector_store_service.embedding_provider,
        vector_collection=vector_store_service.collection_name,
        privacy_mode=str(config["privacy_mode"]),
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
def export_all_data(db: Session = Depends(get_db)) -> JSONResponse:
    payload = {
        "version": 1,
        "knowledge_bases": [_model_dict(item) for item in db.scalars(select(KnowledgeBase))],
        "documents": [
            _model_dict(item, exclude={"file_path"}) for item in db.scalars(select(Document))
        ],
        "chunks": [_model_dict(item) for item in db.scalars(select(DocumentChunk))],
        "conversations": [_model_dict(item) for item in db.scalars(select(Conversation))],
        "messages": [
            {
                **_model_dict(item, exclude={"sources_json"}),
                "sources": _safe_json(item.sources_json, []),
            }
            for item in db.scalars(select(ChatMessage))
        ],
        "learning_records": [
            {
                **_model_dict(item, exclude={"tags_json", "metadata_json"}),
                "tags": _safe_json(item.tags_json, []),
                "metadata": _safe_json(item.metadata_json, {}),
            }
            for item in db.scalars(select(LearningRecord))
        ],
        "settings": {item.key: item.value for item in db.scalars(select(SystemSetting))},
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="knowflow-export.json"'},
    )


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
            continue
    for file_path in file_paths:
        _safe_unlink(file_path)
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


def _safe_json(value: str, default: Any) -> Any:
    try:
        loaded = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


def _safe_unlink(file_path: Path) -> None:
    try:
        file_path.resolve().relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        return
