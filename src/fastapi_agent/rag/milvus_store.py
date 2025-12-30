import uuid
from typing import Any

from fastapi_agent.rag.models import Document
from fastapi_agent.rag.vector_store import VectorStore
from fastapi_agent.rag.embedding_service import EmbeddingService


class MilvusStore(VectorStore):

    def __init__(
        self,
        uri: str,
        embedding_service: EmbeddingService,
        collection_name: str = "memories",
        dimension: int = 1024,
        token: str | None = None,
    ):
        self.uri = uri
        self.embedding_service = embedding_service
        self.collection_name = collection_name
        self.dimension = dimension
        self.token = token
        self._client = None

    async def initialize(self) -> None:
        try:
            from pymilvus import MilvusClient
        except ImportError:
            raise ImportError(
                "pymilvus is required for MilvusStore. "
                "Install with: pip install pymilvus"
            )

        connect_args = {"uri": self.uri}
        if self.token:
            connect_args["token"] = self.token

        self._client = MilvusClient(**connect_args)
        await self._ensure_collection()

    async def _ensure_collection(self) -> None:
        if not self._client:
            raise RuntimeError("Milvus client not connected")

        if self._client.has_collection(self.collection_name):
            return

        from pymilvus import DataType

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self.dimension)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )

        self._client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    async def add_documents(
        self,
        documents: list[Document],
        embeddings: list[list[float]] | None = None,
    ) -> list[str]:
        if not self._client:
            raise RuntimeError("Milvus client not connected")

        if embeddings is None:
            texts = [doc.page_content for doc in documents]
            embeddings = await self.embedding_service.embed_texts(texts)

        ids = []
        data = []
        for doc, embedding in zip(documents, embeddings):
            doc_id = doc.id or str(uuid.uuid4())
            ids.append(doc_id)
            record = {
                "id": doc_id,
                "content": doc.page_content,
                "embedding": embedding,
                **doc.metadata,
            }
            data.append(record)

        self._client.insert(collection_name=self.collection_name, data=data)
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
        return [self._hit_to_document(hit) for hit in results]

    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        embedding = await self.embedding_service.embed_text(query)
        results = await self._search_by_vector(embedding, k, filter)
        return [(self._hit_to_document(hit), hit.get("distance", 0.0)) for hit in results]

    async def _search_by_vector(
        self,
        embedding: list[float],
        k: int,
        filter: dict[str, Any] | None,
    ) -> list[dict]:
        if not self._client:
            raise RuntimeError("Milvus client not connected")

        filter_expr = self._build_filter_expression(filter) if filter else ""

        results = self._client.search(
            collection_name=self.collection_name,
            data=[embedding],
            limit=k,
            filter=filter_expr,
            output_fields=["id", "content", "session_id", "category", "memory_type", "importance"],
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )

        if not results or len(results) == 0:
            return []

        return [dict(hit) for hit in results[0]]

    async def search_hybrid(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> list[tuple[Document, float]]:
        return await self.similarity_search_with_score(query, k, filter)

    async def delete(self, ids: list[str]) -> bool:
        if not self._client:
            raise RuntimeError("Milvus client not connected")

        id_list = ", ".join([f'"{id}"' for id in ids])
        self._client.delete(
            collection_name=self.collection_name,
            filter=f"id in [{id_list}]",
        )
        return True

    async def delete_by_filter(self, filter: dict[str, Any]) -> int:
        if not self._client:
            raise RuntimeError("Milvus client not connected")

        if not filter:
            return 0

        filter_expr = self._build_filter_expression(filter)
        if not filter_expr:
            return 0

        result = self._client.query(
            collection_name=self.collection_name,
            filter=filter_expr,
            output_fields=["id"],
        )
        count = len(result) if result else 0

        if count > 0:
            self._client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
            )

        return count

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def _build_filter_expression(self, filter: dict[str, Any]) -> str:
        if not filter:
            return ""

        conditions = []
        for key, value in filter.items():
            if isinstance(value, str):
                conditions.append(f'{key} == "{value}"')
            elif isinstance(value, bool):
                conditions.append(f"{key} == {str(value).lower()}")
            elif isinstance(value, (int, float)):
                conditions.append(f"{key} == {value}")

        return " and ".join(conditions) if conditions else ""

    def _hit_to_document(self, hit: dict) -> Document:
        entity = hit.get("entity", hit)
        metadata = {}
        for key in ["session_id", "category", "memory_type", "importance"]:
            if key in entity:
                metadata[key] = entity[key]

        return Document(
            id=entity.get("id", ""),
            page_content=entity.get("content", ""),
            metadata=metadata,
        )
