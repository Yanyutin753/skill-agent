"""向量化记忆存储，使用 PostgreSQL + pgvector。"""

import logging
from typing import Optional

import asyncpg
from pgvector.asyncpg import register_vector

from omni_agent.core.config import settings

logger = logging.getLogger(__name__)


class MemoryVectorStore:
    """PostgreSQL 向量记忆存储。

    表结构：
    - id: UUID
    - user_id: 用户ID
    - session_id: 会话ID
    - memory_id: 记忆ID（对应 memory.json 中的 id）
    - content: 记忆内容
    - memory_type: 类型（profile/task/habit）
    - embedding: 向量
    - created_at: 创建时间
    """

    TABLE_NAME = "memory_vectors"

    def __init__(self, user_id: str, session_id: str) -> None:
        self._user_id = user_id
        self._session_id = session_id
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def _get_pool(self) -> asyncpg.Pool:
        """获取或创建连接池。"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                min_size=1,
                max_size=5,
                init=self._init_connection,
            )
        return self._pool

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """初始化连接，注册 pgvector。"""
        await register_vector(conn)

    async def initialize(self) -> None:
        """初始化表结构。"""
        if self._initialized:
            return

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR(100) NOT NULL,
                    session_id VARCHAR(100) NOT NULL,
                    memory_id VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    memory_type VARCHAR(20) NOT NULL,
                    embedding vector({settings.EMBEDDING_DIMENSION}),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(user_id, session_id, memory_id)
                )
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_user_session
                ON {self.TABLE_NAME}(user_id, session_id)
            """)

            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_embedding
                ON {self.TABLE_NAME} USING hnsw (embedding vector_cosine_ops)
            """)

        self._initialized = True

    async def add(
        self,
        memory_id: str,
        content: str,
        memory_type: str,
        embedding: list[float],
    ) -> None:
        """添加向量记忆。"""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.TABLE_NAME}
                (user_id, session_id, memory_id, content, memory_type, embedding)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, session_id, memory_id)
                DO UPDATE SET content = $4, embedding = $6, created_at = NOW()
                """,
                self._user_id,
                self._session_id,
                memory_id,
                content,
                memory_type,
                embedding,
            )

    async def remove(self, memory_id: str) -> None:
        """移除向量记忆。"""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE user_id = $1 AND session_id = $2 AND memory_id = $3
                """,
                self._user_id,
                self._session_id,
                memory_id,
            )

    async def find_similar(
        self,
        embedding: list[float],
        memory_type: str,
        threshold: float = 0.85,
        top_k: int = 1,
    ) -> list[tuple[str, float, str]]:
        """查找相似记忆。

        Returns:
            [(memory_id, similarity, content), ...]
        """
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    memory_id,
                    content,
                    1 - (embedding <=> $1::vector) as similarity
                FROM {self.TABLE_NAME}
                WHERE user_id = $2
                  AND session_id = $3
                  AND memory_type = $4
                  AND 1 - (embedding <=> $1::vector) >= $5
                ORDER BY embedding <=> $1::vector
                LIMIT $6
                """,
                embedding,
                self._user_id,
                self._session_id,
                memory_type,
                threshold,
                top_k,
            )

            return [
                (row["memory_id"], float(row["similarity"]), row["content"])
                for row in rows
            ]

    async def clear_by_type(self, memory_type: str) -> int:
        """清除指定类型的所有向量。"""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE user_id = $1 AND session_id = $2 AND memory_type = $3
                """,
                self._user_id,
                self._session_id,
                memory_type,
            )
            count = int(result.split()[-1]) if result else 0
            return count

    async def clear_all(self) -> None:
        """清除当前会话的所有向量。"""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE user_id = $1 AND session_id = $2
                """,
                self._user_id,
                self._session_id,
            )

    async def count(self, memory_type: Optional[str] = None) -> int:
        """统计向量数量。"""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            if memory_type:
                row = await conn.fetchrow(
                    f"""
                    SELECT COUNT(*) as cnt FROM {self.TABLE_NAME}
                    WHERE user_id = $1 AND session_id = $2 AND memory_type = $3
                    """,
                    self._user_id,
                    self._session_id,
                    memory_type,
                )
            else:
                row = await conn.fetchrow(
                    f"""
                    SELECT COUNT(*) as cnt FROM {self.TABLE_NAME}
                    WHERE user_id = $1 AND session_id = $2
                    """,
                    self._user_id,
                    self._session_id,
                )
            return row["cnt"] if row else 0

    async def close(self) -> None:
        """关闭连接池。"""
        if self._pool:
            await self._pool.close()
            self._pool = None
