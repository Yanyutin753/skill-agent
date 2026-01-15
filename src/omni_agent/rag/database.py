"""Database manager for RAG knowledge base using PostgreSQL + pgvector."""

import json
import uuid
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from omni_agent.core.config import settings


class DatabaseManager:
    """Manages PostgreSQL connection and operations for RAG knowledge base."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize database connection pool."""
        self._pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=2,
            max_size=10,
            init=self._init_connection,
        )

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize connection with pgvector extension."""
        await register_vector(conn)

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def initialize_schema(self) -> None:
        """Create database tables and indexes if they don't exist."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # Create documents table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    filename VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    file_size INTEGER NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'
                )
            """)

            # Create chunks table with vector column and tsvector for full-text search
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    embedding vector({settings.EMBEDDING_DIMENSION}),
                    content_tsv tsvector,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    metadata JSONB DEFAULT '{{}}'
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id
                ON chunks(document_id)
            """)

            # Create vector similarity index (HNSW - works well with any data size)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                ON chunks USING hnsw (embedding vector_cosine_ops)
            """)

            # Create GIN index for full-text search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv
                ON chunks USING gin(content_tsv)
            """)

    async def insert_document(
        self,
        filename: str,
        file_type: str,
        file_size: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert a new document record."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        doc_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, file_size, metadata)
                VALUES ($1, $2, $3, $4, $5)
                """,
                uuid.UUID(doc_id),
                filename,
                file_type,
                file_size,
                json.dumps(metadata or {}),
            )
        return doc_id

    async def insert_chunks(
        self,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Insert multiple chunks for a document."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            # Batch insert chunks with tsvector for full-text search
            # Use 'simple' config for better multilingual support (Chinese + English)
            await conn.executemany(
                """
                INSERT INTO chunks (id, document_id, content, chunk_index, embedding, content_tsv, metadata)
                VALUES ($1, $2, $3, $4, $5, to_tsvector('simple', $3), $6)
                """,
                [
                    (
                        uuid.uuid4(),
                        uuid.UUID(document_id),
                        chunk["content"],
                        chunk["chunk_index"],
                        chunk["embedding"],
                        json.dumps(chunk.get("metadata", {})),
                    )
                    for chunk in chunks
                ],
            )

            # Update document chunk count
            await conn.execute(
                """
                UPDATE documents SET chunk_count = $1 WHERE id = $2
                """,
                len(chunks),
                uuid.UUID(document_id),
            )

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks using vector similarity."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    c.id,
                    c.content,
                    c.chunk_index,
                    c.metadata,
                    d.filename,
                    d.file_type,
                    1 - (c.embedding <=> $1::vector) as similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE 1 - (c.embedding <=> $1::vector) > $3
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                query_embedding,
                top_k,
                threshold,
            )

            return [
                {
                    "id": str(row["id"]),
                    "content": row["content"],
                    "chunk_index": row["chunk_index"],
                    "metadata": row["metadata"],
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ]

    async def search_keyword(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for chunks using full-text search + ILIKE for Chinese support."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            # Combine tsvector search (for English) and ILIKE (for Chinese)
            # This handles multilingual content without requiring special extensions
            rows = await conn.fetch(
                """
                SELECT
                    c.id,
                    c.content,
                    c.chunk_index,
                    c.metadata,
                    d.filename,
                    d.file_type,
                    CASE
                        WHEN c.content_tsv @@ plainto_tsquery('simple', $1)
                        THEN ts_rank_cd(c.content_tsv, plainto_tsquery('simple', $1))
                        ELSE 0.1
                    END as rank
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.content_tsv @@ plainto_tsquery('simple', $1)
                   OR c.content ILIKE '%' || $1 || '%'
                ORDER BY rank DESC, c.content ILIKE '%' || $1 || '%' DESC
                LIMIT $2
                """,
                query,
                top_k,
            )

            return [
                {
                    "id": str(row["id"]),
                    "content": row["content"],
                    "chunk_index": row["chunk_index"],
                    "metadata": row["metadata"],
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "rank": float(row["rank"]),
                }
                for row in rows
            ]

    async def search_hybrid(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 5,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining semantic and keyword search using RRF.

        Args:
            query: Search query text for keyword search
            query_embedding: Query embedding vector for semantic search
            top_k: Number of results to return
            semantic_weight: Weight for semantic search scores (0-1)
            keyword_weight: Weight for keyword search scores (0-1)
            rrf_k: RRF constant (default 60, higher = more weight to lower ranks)

        Returns:
            Combined and re-ranked results
        """
        if not self._pool:
            raise RuntimeError("Database not connected")

        # Fetch more candidates for better fusion
        fetch_k = top_k * 3

        async with self._pool.acquire() as conn:
            # Single query combining both search methods with RRF fusion
            rows = await conn.fetch(
                """
                WITH semantic_results AS (
                    SELECT
                        c.id,
                        c.content,
                        c.chunk_index,
                        c.metadata,
                        c.document_id,
                        ROW_NUMBER() OVER (ORDER BY c.embedding <=> $1::vector) as semantic_rank,
                        1 - (c.embedding <=> $1::vector) as semantic_score
                    FROM chunks c
                    ORDER BY c.embedding <=> $1::vector
                    LIMIT $3
                ),
                keyword_results AS (
                    SELECT
                        c.id,
                        ROW_NUMBER() OVER (
                            ORDER BY
                                CASE WHEN c.content_tsv @@ plainto_tsquery('simple', $2)
                                     THEN ts_rank_cd(c.content_tsv, plainto_tsquery('simple', $2))
                                     ELSE 0.1 END DESC,
                                c.content ILIKE '%' || $2 || '%' DESC
                        ) as keyword_rank,
                        CASE WHEN c.content_tsv @@ plainto_tsquery('simple', $2)
                             THEN ts_rank_cd(c.content_tsv, plainto_tsquery('simple', $2))
                             ELSE 0.1 END as keyword_score
                    FROM chunks c
                    WHERE c.content_tsv @@ plainto_tsquery('simple', $2)
                       OR c.content ILIKE '%' || $2 || '%'
                    LIMIT $3
                ),
                combined AS (
                    SELECT
                        s.id,
                        s.content,
                        s.chunk_index,
                        s.metadata,
                        s.document_id,
                        s.semantic_score,
                        COALESCE(k.keyword_score, 0) as keyword_score,
                        -- RRF Score: sum of 1/(k + rank) for each ranking
                        ($4 * (1.0 / ($6 + s.semantic_rank))) +
                        ($5 * COALESCE(1.0 / ($6 + k.keyword_rank), 0)) as rrf_score
                    FROM semantic_results s
                    LEFT JOIN keyword_results k ON s.id = k.id
                )
                SELECT
                    c.id,
                    c.content,
                    c.chunk_index,
                    c.metadata,
                    d.filename,
                    d.file_type,
                    c.semantic_score,
                    c.keyword_score,
                    c.rrf_score
                FROM combined c
                JOIN documents d ON c.document_id = d.id
                ORDER BY c.rrf_score DESC
                LIMIT $7
                """,
                query_embedding,
                query,
                fetch_k,
                semantic_weight,
                keyword_weight,
                rrf_k,
                top_k,
            )

            return [
                {
                    "id": str(row["id"]),
                    "content": row["content"],
                    "chunk_index": row["chunk_index"],
                    "metadata": row["metadata"],
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "semantic_score": float(row["semantic_score"]),
                    "keyword_score": float(row["keyword_score"]),
                    "rrf_score": float(row["rrf_score"]),
                }
                for row in rows
            ]

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the knowledge base."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, filename, file_type, file_size, chunk_count, created_at, metadata
                FROM documents
                ORDER BY created_at DESC
                """
            )

            return [
                {
                    "id": str(row["id"]),
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "file_size": row["file_size"],
                    "chunk_count": row["chunk_count"],
                    "created_at": row["created_at"].isoformat(),
                    "metadata": row["metadata"],
                }
                for row in rows
            ]

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1",
                uuid.UUID(document_id),
            )
            return result == "DELETE 1"

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Get a document by ID."""
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, filename, file_type, file_size, chunk_count, created_at, metadata
                FROM documents
                WHERE id = $1
                """,
                uuid.UUID(document_id),
            )

            if row:
                return {
                    "id": str(row["id"]),
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "file_size": row["file_size"],
                    "chunk_count": row["chunk_count"],
                    "created_at": row["created_at"].isoformat(),
                    "metadata": row["metadata"],
                }
            return None


# Global database manager instance
db_manager = DatabaseManager()
