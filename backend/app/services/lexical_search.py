import logging
import re
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection

logger = logging.getLogger(__name__)

ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TOKEN_SCAN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def to_search_text(text: str) -> str:
    tokens: list[str] = []
    for match in TOKEN_SCAN_RE.finditer(text or ""):
        token = match.group(0)
        if ASCII_WORD_RE.fullmatch(token):
            tokens.append(token)
        else:
            chars = [char for char in token if _is_cjk(char)]
            tokens.extend(chars[index] + chars[index + 1] for index in range(len(chars) - 1))
    return " ".join(tokens)


def _build_search_text(content: str, section_path: str = "") -> str:
    return f"{to_search_text(content)} {to_search_text(section_path or '')}".strip()


FTS_TABLE_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    text,
    content='document_chunk',
    content_rowid='id',
    tokenize='unicode61'
)
""".strip()

FTS_TRIGGER_DDLS = [
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_ai AFTER INSERT ON document_chunk BEGIN
      INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
    END
    """.strip(),
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_ad AFTER DELETE ON document_chunk BEGIN
      INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
    END
    """.strip(),
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_au AFTER UPDATE ON document_chunk BEGIN
      INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
      INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
    END
    """.strip(),
]

BACKFILL_BATCH_SIZE = 500


def fts5_available(engine: Engine) -> bool:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT compile_options FROM pragma_compile_options"
        ).fetchall()
    return any("FTS5" in str(row[0]) for row in rows)


def ensure_lexical_index(engine: Engine) -> bool:
    if not fts5_available(engine):
        logger.warning("SQLite FTS5 is unavailable; lexical channel will use LIKE fallback.")
        return False
    with engine.begin() as connection:
        connection.exec_driver_sql(FTS_TABLE_DDL)
        for trigger_ddl in FTS_TRIGGER_DDLS:
            connection.exec_driver_sql(trigger_ddl)
        # SQLite < 3.46 quirk: a 'delete' command against a never-written FTS5
        # external-content index raises "database disk image is malformed".
        # delete-all + populate keeps the index initialized (idempotent,
        # self-healing) so trigger delete commands always land on live segments.
        # Zero-row tables stay virgin, but no delete can fire without a prior
        # insert trigger, which itself initializes the index.
        connection.exec_driver_sql("INSERT INTO chunk_fts(chunk_fts) VALUES('delete-all')")
        connection.exec_driver_sql(
            "INSERT INTO chunk_fts(rowid, text) SELECT id, search_text FROM document_chunk"
        )
    return True


def ensure_chunk_columns(engine: Engine) -> None:
    expected = {"section_id": "INTEGER", "search_text": "TEXT DEFAULT ''"}
    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(document_chunk)").fetchall()
        }
        for column, ddl in expected.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE document_chunk ADD COLUMN {column} {ddl}")
                logger.info("Added missing column document_chunk.%s", column)


def backfill_search_text(db: Session, batch_size: int = BACKFILL_BATCH_SIZE) -> int:
    total = 0
    while True:
        ids = list(
            db.scalars(
                select(DocumentChunk.id)
                .where(DocumentChunk.search_text == "")
                .limit(batch_size)
            )
        )
        if not ids:
            break
        chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ids))))
        section_ids = {c.section_id for c in chunks if c.section_id is not None}
        paths: dict[int, str] = {}
        if section_ids:
            paths = dict(
                db.execute(
                    select(DocumentSection.id, DocumentSection.section_path).where(
                        DocumentSection.id.in_(section_ids)
                    )
                ).all()
            )
        for chunk in chunks:
            path = paths.get(chunk.section_id, "") if chunk.section_id else ""
            chunk.search_text = _build_search_text(chunk.content, path)
        db.commit()
        total += len(chunks)
    if total:
        logger.info("Backfilled search_text for %s chunks", total)
    return total


FTS_SEARCH_SQL = """
SELECT c.id AS chunk_id, c.kb_id AS kb_id, c.document_id AS document_id,
       c.chunk_index AS chunk_index, c.content AS content, c.section_id AS section_id,
       bm25(chunk_fts) AS rank_value
FROM chunk_fts JOIN document_chunk AS c ON c.id = chunk_fts.rowid
WHERE chunk_fts MATCH :terms AND c.kb_id = :kb_id
ORDER BY rank_value LIMIT :limit
""".strip()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_lexical(
    db: Session, kb_id: int, query: str, top_k: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    terms = to_search_text(query)
    if not terms:
        return [], {"returned": 0, "best": 0.0, "fallback": None}
    limit = max(top_k * 2, 10)
    # OR semantics: bigram queries rarely share every pair with a hit
    # (e.g. question 是什么 vs document 是主节点); bm25 ranks, RRF fuses.
    match_query = " OR ".join(terms.split())
    try:
        rows = (
            db.execute(text(FTS_SEARCH_SQL), {"terms": match_query, "kb_id": kb_id, "limit": limit})
            .mappings()
            .all()
        )
    except OperationalError:
        logger.warning("chunk_fts unavailable; lexical channel uses LIKE fallback.")
        return _search_like(db, kb_id, query, limit)
    if not rows:
        return [], {"returned": 0, "best": 0.0, "fallback": None}
    ranks = [float(row["rank_value"]) for row in rows]
    lowest, highest = min(ranks), max(ranks)
    section_ids = {row["section_id"] for row in rows if row["section_id"] is not None}
    paths: dict[int, str] = {}
    if section_ids:
        paths = dict(
            db.execute(
                select(DocumentSection.id, DocumentSection.section_path).where(
                    DocumentSection.id.in_(section_ids)
                )
            ).all()
        )
    hits = [
        {
            "chunk_id": int(row["chunk_id"]),
            "document_id": int(row["document_id"]),
            "kb_id": int(row["kb_id"]),
            "chunk_index": int(row["chunk_index"]),
            "content": str(row["content"]),
            "score": 1.0 if highest == lowest else (highest - float(row["rank_value"])) / (highest - lowest),
            "section_path": paths.get(row["section_id"], "") if row["section_id"] else "",
        }
        for row in rows
    ]
    return hits, {"returned": len(hits), "best": hits[0]["score"], "fallback": None}


def _search_like(
    db: Session, kb_id: int, query: str, limit: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pattern = f"%{_escape_like(query)}%"
    rows = (
        db.execute(
            select(DocumentChunk, DocumentSection.section_path)
            .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
            .where(DocumentChunk.kb_id == kb_id)
            .where(
                or_(
                    DocumentChunk.content.like(pattern, escape="\\"),
                    DocumentSection.section_path.like(pattern, escape="\\"),
                )
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(limit)
        )
        .all()
    )
    hits = [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "kb_id": chunk.kb_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": 1.0 / (rank + 1),
            "section_path": section_path or "",
        }
        for rank, (chunk, section_path) in enumerate(rows)
    ]
    return hits, {"returned": len(hits), "best": hits[0]["score"] if hits else 0.0, "fallback": "like"}
