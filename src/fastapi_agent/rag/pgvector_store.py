import json
import uuid
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from fastapi_agent.rag.models import Document
from fastapi_agent.rag.vector_store import VectorStore
from fastapi_agent.rag.embedding_service import EmbeddingService


class PGVectorStore(VectorStore):

    def __init__(
        self,
        dsn: str,
        embedding_service: EmbeddingService,
        table_name: str = "memories",
        dimension: int = 1024,
    ):
        self.dsn = dsn
        self.embedding_service = embedding_service
        self.table_name = table_name
        self.dimension = dimension
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=10,
            init=self._init_connection,
        )
        await self._create_schema()

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        await register_vector(conn)

    async def _create_schema(self) -> None:
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    content TEXT NOT NULL,
                    embedding vector({self.dimension}),
                    content_tsv tsvector,
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_embedding
                ON {self.table_name} USING hnsw (embedding vector_cosine_ops)
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_content_tsv
                ON {self.table_name} USING gin(content_tsv)
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_session_id
                ON {self.table_name} ((metadata->>'session_id'))
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_memory_type
                ON {self.table_name} ((metadata->>'memory_type'))
            """)

    async def add_documents(
        self,
        documents: list[Document],
        embeddings: list[list[float]] | None = None,
    ) -> list[str]:
        if not self._pool:
            raise RuntimeError("Database not connected")

        if embeddings is None:
            texts = [doc.page_content for doc in documents]
            embeddings = await self.embedding_service.embed_texts(texts)

        ids = []
        async with self._pool.acquire() as conn:
            for doc, embedding in zip(documents, embeddings):
                doc_id = doc.id or str(uuid.uuid4())
                await conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (id, content, embedding, content_tsv, metadata)
                    VALUES ($1, $2, $3, to_tsvector('simple', $2), $4)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        content_tsv = EXCLUDED.content_tsv,
                        metadata = EXCLUDED.metadata
                    """,
                    uuid.UUID(doc_id),
                    doc.page_content,
                    embedding,
                    json.dumps(doc.metadata),
                )
                ids.append(doc_id)

        return ids

    async def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[Document]:
        embedding = await self.embedding_service.embed_text(query)
        return await self.similarity_search_by_vector(embedding, k, filter)

    async def similarity_search_by_vector(
        self,
        embedding: list[float],
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[Document]:
        results = await self._search_by_vector(embedding, k, filter)
        return [self._row_to_document(row) for row in results]

    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        embedding = await self.embedding_service.embed_text(query)
        results = await self._search_by_vector(embedding, k, filter)
        return [(self._row_to_document(row), float(row["similarity"])) for row in results]

    async def _search_by_vector(
        self,
        embedding: list[float],
        k: int,
        filter: dict[str, Any] | None,
    ) -> list[dict]:
        if not self._pool:
            raise RuntimeError("Database not connected")

        where_clauses = []
        params: list[Any] = [embedding, k]
        param_idx = 3

        if filter:
            for key, value in filter.items():
                where_clauses.append(f"metadata->>'{key}' = ${param_idx}")
                params.append(str(value))
                param_idx += 1

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    id,
                    content,
                    metadata,
                    1 - (embedding <=> $1::vector) as similarity
                FROM {self.table_name}
                {where_sql}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                *params,
            )
            return [dict(row) for row in rows]

    async def search_hybrid(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[tuple[Document, float]]:
        if not self._pool:
            raise RuntimeError("Database not connected")

        embedding = await self.embedding_service.embed_text(query)
        fetch_k = k * 3

        where_clauses = []
        params: list[Any] = [embedding, query, fetch_k, k]
        param_idx = 5

        if filter:
            for key, value in filter.items():
                where_clauses.append(f"metadata->>'{key}' = ${param_idx}")
                params.append(str(value))
                param_idx += 1

        filter_sql = ""
        if where_clauses:
            filter_sql = "WHERE " + " AND ".join(where_clauses)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH semantic_results AS (
                    SELECT
                        id, content, metadata,
                        ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) as semantic_rank,
                        1 - (embedding <=> $1::vector) as semantic_score
                    FROM {self.table_name}
                    {filter_sql}
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                ),
                keyword_results AS (
                    SELECT
                        id, content, metadata,
                        ROW_NUMBER() OVER (ORDER BY
                            CASE WHEN content_tsv @@ plainto_tsquery('simple', $2)
                            THEN ts_rank_cd(content_tsv, plainto_tsquery('simple', $2))
                            ELSE 0.1 END DESC
                        ) as keyword_rank,
                        CASE WHEN content_tsv @@ plainto_tsquery('simple', $2)
                        THEN ts_rank_cd(content_tsv, plainto_tsquery('simple', $2))
                        ELSE 0.1 END as keyword_score
                    FROM {self.table_name}
                    {filter_sql}
                    WHERE content_tsv @@ plainto_tsquery('simple', $2)
                       OR content ILIKE '%' || $2 || '%'
                    LIMIT $3
                ),
                combined AS (
                    SELECT
                        COALESCE(s.id, k.id) as id,
                        COALESCE(s.content, k.content) as content,
                        COALESCE(s.metadata, k.metadata) as metadata,
                        COALESCE(s.semantic_score, 0) as semantic_score,
                        COALESCE(k.keyword_score, 0) as keyword_score,
                        {semantic_weight}/(60 + COALESCE(s.semantic_rank, 1000)) +
                        {keyword_weight}/(60 + COALESCE(k.keyword_rank, 1000)) as rrf_score
                    FROM semantic_results s
                    FULL OUTER JOIN keyword_results k ON s.id = k.id
                )
                SELECT * FROM combined
                ORDER BY rrf_score DESC
                LIMIT $4
                """,
                *params,
            )

            return [
                (self._row_to_document(dict(row)), float(row["rrf_score"]))
                for row in rows
            ]

    async def delete(self, ids: list[str]) -> bool:
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {self.table_name} WHERE id = ANY($1::uuid[])",
                [uuid.UUID(id) for id in ids],
            )
            return "DELETE" in result

    async def delete_by_filter(self, filter: dict[str, Any]) -> int:
        if not self._pool:
            raise RuntimeError("Database not connected")

        where_clauses = []
        params: list[Any] = []
        param_idx = 1

        for key, value in filter.items():
            where_clauses.append(f"metadata->>'{key}' = ${param_idx}")
            params.append(str(value))
            param_idx += 1

        if not where_clauses:
            return 0

        where_sql = " AND ".join(where_clauses)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {self.table_name} WHERE {where_sql}",
                *params,
            )
            count = int(result.split()[-1]) if result else 0
            return count

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _row_to_document(self, row: dict) -> Document:
        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Document(
            id=str(row["id"]),
            page_content=row["content"],
            metadata=metadata,
        )

    async def list_by_metadata(
        self,
        key: str,
        distinct: bool = True,
    ) -> list[dict]:
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            if distinct:
                rows = await conn.fetch(
                    f"""
                    SELECT DISTINCT metadata->>'{key}' as value,
                           COUNT(*) as count,
                           MIN(created_at) as created_at
                    FROM {self.table_name}
                    WHERE metadata->>'{key}' IS NOT NULL
                    GROUP BY metadata->>'{key}'
                    ORDER BY MIN(created_at) DESC
                    """,
                )
                return [dict(row) for row in rows]
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT id, content, metadata, created_at
                    FROM {self.table_name}
                    WHERE metadata->>'{key}' IS NOT NULL
                    ORDER BY created_at DESC
                    """,
                )
                return [dict(row) for row in rows]

    async def get_by_metadata_value(
        self,
        key: str,
        value: str,
    ) -> list[Document]:
        if not self._pool:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, content, metadata
                FROM {self.table_name}
                WHERE metadata->>'{key}' = $1
                ORDER BY (metadata->>'chunk_index')::int
                """,
                value,
            )
            return [self._row_to_document(dict(row)) for row in rows]
