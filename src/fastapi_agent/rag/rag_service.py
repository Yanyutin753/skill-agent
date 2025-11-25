"""RAG service for knowledge base operations."""

from typing import Any, BinaryIO

from fastapi_agent.core.config import settings
from fastapi_agent.rag.database import DatabaseManager, db_manager
from fastapi_agent.rag.document_processor import DocumentProcessor, document_processor
from fastapi_agent.rag.embedding_service import EmbeddingService, embedding_service


class RAGService:
    """High-level service for RAG operations."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        embedder: EmbeddingService | None = None,
        processor: DocumentProcessor | None = None,
    ) -> None:
        self.db = db or db_manager
        self.embedder = embedder or embedding_service
        self.processor = processor or document_processor

    async def initialize(self) -> None:
        """Initialize RAG service (connect to database and create schema)."""
        await self.db.connect()
        await self.db.initialize_schema()

    async def shutdown(self) -> None:
        """Shutdown RAG service."""
        await self.db.disconnect()

    async def add_document(
        self,
        file: BinaryIO,
        filename: str,
        file_size: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a document to the knowledge base.

        Returns:
            Document info with id and chunk count
        """
        # Validate file type
        if not self.processor.is_supported(filename):
            raise ValueError(
                f"Unsupported file type. Supported: {list(self.processor.SUPPORTED_TYPES.keys())}"
            )

        file_type = self.processor.get_file_type(filename)

        # Process file: extract text and chunk
        _, chunks = await self.processor.process_file(file, filename)

        if not chunks:
            raise ValueError("No content could be extracted from the file")

        # Generate embeddings for all chunks
        chunk_texts = [chunk["content"] for chunk in chunks]
        embeddings = await self.embedder.embed_texts(chunk_texts)

        # Add embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        # Store in database
        doc_id = await self.db.insert_document(
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            metadata=metadata,
        )

        await self.db.insert_chunks(doc_id, chunks)

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
        """Search knowledge base for relevant content.

        Args:
            query: Search query text
            top_k: Number of results to return (default from settings)
            mode: Search mode - "hybrid" (default), "semantic", or "keyword"
            semantic_weight: Weight for semantic search in hybrid mode (0-1)
            keyword_weight: Weight for keyword search in hybrid mode (0-1)

        Returns:
            List of relevant chunks with scores
        """
        top_k = top_k or settings.RAG_TOP_K

        if mode == "keyword":
            # Pure keyword search
            results = await self.db.search_keyword(query=query, top_k=top_k)
            # Normalize output format
            for r in results:
                r["similarity"] = r.pop("rank", 0)
            return results

        # Generate query embedding for semantic/hybrid search
        query_embedding = await self.embedder.embed_text(query)

        if mode == "semantic":
            # Pure semantic search
            return await self.db.search_similar(
                query_embedding=query_embedding,
                top_k=top_k,
            )

        # Default: Hybrid search (semantic + keyword with RRF)
        results = await self.db.search_hybrid(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

        # Add unified similarity score based on RRF
        for r in results:
            r["similarity"] = r["rrf_score"]

        return results

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the knowledge base."""
        return await self.db.list_documents()

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Get document by ID."""
        return await self.db.get_document(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document from the knowledge base."""
        return await self.db.delete_document(document_id)


# Global RAG service instance
rag_service = RAGService()
