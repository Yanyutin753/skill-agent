"""RAG service for knowledge base operations using PGVectorStore."""

import uuid
from typing import Any, BinaryIO

from fastapi_agent.core.config import settings
from fastapi_agent.rag.models import Document
from fastapi_agent.rag.pgvector_store import PGVectorStore
from fastapi_agent.rag.document_processor import DocumentProcessor, document_processor
from fastapi_agent.rag.embedding_service import EmbeddingService, embedding_service


class RAGService:
    def __init__(
        self,
        store: PGVectorStore | None = None,
        embedder: EmbeddingService | None = None,
        processor: DocumentProcessor | None = None,
    ) -> None:
        self.embedder = embedder or embedding_service
        self.processor = processor or document_processor
        self._store = store
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        dsn = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        self._store = PGVectorStore(
            dsn=dsn,
            embedding_service=self.embedder,
            table_name="rag_chunks",
            dimension=settings.EMBEDDING_DIMENSION,
        )
        await self._store.initialize()
        self._initialized = True

    async def shutdown(self) -> None:
        if self._store:
            await self._store.close()
            self._initialized = False

    @property
    def store(self) -> PGVectorStore:
        if not self._store:
            raise RuntimeError("RAG service not initialized")
        return self._store

    async def add_document(
        self,
        file: BinaryIO,
        filename: str,
        file_size: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.processor.is_supported(filename):
            raise ValueError(
                f"Unsupported file type. Supported: {list(self.processor.SUPPORTED_TYPES.keys())}"
            )

        file_type = self.processor.get_file_type(filename)
        _, chunks = await self.processor.process_file(file, filename)

        if not chunks:
            raise ValueError("No content could be extracted from the file")

        doc_id = str(uuid.uuid4())
        base_metadata = {
            "document_id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
            **(metadata or {}),
        }

        documents = []
        for chunk in chunks:
            chunk_metadata = {
                **base_metadata,
                "chunk_index": chunk["chunk_index"],
                **chunk.get("metadata", {}),
            }
            documents.append(Document(
                page_content=chunk["content"],
                metadata=chunk_metadata,
            ))

        await self.store.add_documents(documents)

        return {
            "id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
            "chunk_count": len(chunks),
        }

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: str = "hybrid",
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[dict[str, Any]]:
        top_k = top_k or settings.RAG_TOP_K

        if mode == "keyword":
            results = await self.store.search_hybrid(
                query=query,
                k=top_k,
                semantic_weight=0.0,
                keyword_weight=1.0,
            )
            return [
                {
                    "id": doc.id,
                    "content": doc.page_content,
                    "filename": doc.metadata.get("filename"),
                    "file_type": doc.metadata.get("file_type"),
                    "chunk_index": doc.metadata.get("chunk_index"),
                    "metadata": doc.metadata,
                    "similarity": score,
                }
                for doc, score in results
            ]

        if mode == "semantic":
            results = await self.store.similarity_search_with_score(query, k=top_k)
            return [
                {
                    "id": doc.id,
                    "content": doc.page_content,
                    "filename": doc.metadata.get("filename"),
                    "file_type": doc.metadata.get("file_type"),
                    "chunk_index": doc.metadata.get("chunk_index"),
                    "metadata": doc.metadata,
                    "similarity": score,
                }
                for doc, score in results
            ]

        results = await self.store.search_hybrid(
            query=query,
            k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )
        return [
            {
                "id": doc.id,
                "content": doc.page_content,
                "filename": doc.metadata.get("filename"),
                "file_type": doc.metadata.get("file_type"),
                "chunk_index": doc.metadata.get("chunk_index"),
                "metadata": doc.metadata,
                "similarity": score,
            }
            for doc, score in results
        ]

    async def list_documents(self) -> list[dict[str, Any]]:
        rows = await self.store.list_by_metadata("document_id", distinct=True)
        results = []
        for row in rows:
            doc_id = row["value"]
            docs = await self.store.get_by_metadata_value("document_id", doc_id)
            if docs:
                first_doc = docs[0]
                results.append({
                    "id": doc_id,
                    "filename": first_doc.metadata.get("filename"),
                    "file_type": first_doc.metadata.get("file_type"),
                    "file_size": first_doc.metadata.get("file_size"),
                    "chunk_count": row["count"],
                    "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    "metadata": {k: v for k, v in first_doc.metadata.items()
                                if k not in ("document_id", "filename", "file_type", "file_size", "chunk_index")},
                })
        return results

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        docs = await self.store.get_by_metadata_value("document_id", document_id)
        if not docs:
            return None
        first_doc = docs[0]
        return {
            "id": document_id,
            "filename": first_doc.metadata.get("filename"),
            "file_type": first_doc.metadata.get("file_type"),
            "file_size": first_doc.metadata.get("file_size"),
            "chunk_count": len(docs),
            "metadata": {k: v for k, v in first_doc.metadata.items()
                        if k not in ("document_id", "filename", "file_type", "file_size", "chunk_index")},
        }

    async def delete_document(self, document_id: str) -> bool:
        count = await self.store.delete_by_filter({"document_id": document_id})
        return count > 0


rag_service = RAGService()
