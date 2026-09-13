from app.models.document import Document
from sqlalchemy.orm import Session


def recover_interrupted_documents(db: Session) -> int:
    documents = db.query(Document).filter(Document.status == "processing").all()
    for document in documents:
        document.status = "failed"
        document.error_message = "处理任务因应用中断而停止，请点击重试。"
    if documents:
        db.commit()
    return len(documents)
