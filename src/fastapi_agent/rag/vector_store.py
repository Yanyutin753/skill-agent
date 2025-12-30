from abc import ABC, abstractmethod
from typing import Any

from fastapi_agent.rag.models import Document


class VectorStore(ABC):

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def add_documents(
        self,
        documents: list[Document],
        embeddings: list[list[float]] | None = None,
    ) -> list[str]:
        pass

    @abstractmethod
    async def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[Document]:
        pass

    @abstractmethod
    async def similarity_search_by_vector(
        self,
        embedding: list[float],
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[Document]:
        pass

    @abstractmethod
    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        pass

    @abstractmethod
    async def delete(self, ids: list[str]) -> bool:
        pass

    @abstractmethod
    async def delete_by_filter(self, filter: dict[str, Any]) -> int:
        pass

    async def max_marginal_relevance_search(
        self,
        query: str,
        k: int = 4,
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
        filter: dict[str, Any] | None = None,
    ) -> list[Document]:
        raise NotImplementedError("MMR search not implemented for this store")

    @classmethod
    async def from_documents(
        cls,
        documents: list[Document],
        embedding_service: Any,
        **kwargs,
    ) -> "VectorStore":
        raise NotImplementedError("from_documents not implemented for this store")

    async def close(self) -> None:
        pass
