import logging
from typing import Any

import chromadb
from app.core.database import BASE_DIR
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import embedding_service

CHROMA_DIR = BASE_DIR / "storage" / "chroma"
UPSERT_BATCH_SIZE = 100
logger = logging.getLogger(__name__)


class VectorStoreService:
    def __init__(self) -> None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    def _collection_for(self, index_name: str):
        return self.client.get_or_create_collection(
            name=_collection_name(index_name),
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self):
        return self._collection_for(embedding_service.index_name)

    @property
    def collection_name(self) -> str:
        return _collection_name(embedding_service.index_name)

    @property
    def embedding_provider(self) -> str:
        return embedding_service.index_name

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return

        documents = [chunk.content for chunk in chunks]
        embeddings = embedding_service.embed_texts(documents)
        collection = self.collection
        ids = [_chunk_vector_id(chunk.id) for chunk in chunks]
        metadatas = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "kb_id": chunk.kb_id,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ]

        for start in range(0, len(ids), UPSERT_BATCH_SIZE):
            end = start + UPSERT_BATCH_SIZE
            collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
        logger.info("Indexed %s chunks in collection %s", len(chunks), collection.name)

    def delete_chunks(self, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return
        for collection in self._known_collections():
            collection.delete(ids=[_chunk_vector_id(chunk_id) for chunk_id in chunk_ids])

    def delete_document(self, document_id: int) -> None:
        for collection in self._known_collections():
            collection.delete(where={"document_id": document_id})

    def delete_knowledge_base(self, kb_id: int) -> None:
        for collection in self._known_collections():
            collection.delete(where={"kb_id": kb_id})

    def search(self, kb_id: int, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        collection = self.collection
        fallback = embedding_service.fallback
        fallback_collection = self._collection_for(fallback.index_name)
        if collection.count() == 0 and fallback_collection.count() > 0:
            embedding_service.use_fallback()
        query_embedding = embedding_service.embed_text(query)
        collection = self.collection
        if collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"kb_id": kb_id},
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        matches: list[dict[str, Any]] = []
        for document, metadata, distance in zip(documents, metadatas, distances, strict=False):
            matches.append(
                {
                    "chunk_id": int(metadata["chunk_id"]),
                    "document_id": int(metadata["document_id"]),
                    "kb_id": int(metadata["kb_id"]),
                    "chunk_index": int(metadata["chunk_index"]),
                    "content": document,
                    "score": max(0.0, 1.0 - float(distance)),
                }
            )
        return matches

    def _known_collections(self) -> list[Any]:
        index_names = {embedding_service.primary.index_name, embedding_service.fallback.index_name}
        return [self._collection_for(index_name) for index_name in index_names]


def _chunk_vector_id(chunk_id: int) -> str:
    return f"chunk-{chunk_id}"


def _collection_name(index_name: str) -> str:
    return "knowflow_chunks" if index_name == "hashing_v1" else f"knowflow_chunks_{index_name}"


vector_store_service = VectorStoreService()
