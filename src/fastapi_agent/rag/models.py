from dataclasses import dataclass, field
from typing import Any
import time
import uuid


@dataclass
class Document:
    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())


class MemoryScope:
    USER = "user"
    PROJECT = "project"
    SESSION = "session"


@dataclass
class Memory:
    content: str
    category: str = "general"
    scope: str = "project"
    importance: float = 1.0
    user_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "agent"
    access_count: int = 0
    last_accessed_at: float | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_document(self) -> Document:
        return Document(
            page_content=self.content,
            metadata={
                "category": self.category,
                "scope": self.scope,
                "importance": self.importance,
                "user_id": self.user_id,
                "project_id": self.project_id,
                "session_id": self.session_id,
                "source": self.source,
                "access_count": self.access_count,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                **self.metadata,
            },
            id=self.id,
        )

    @classmethod
    def from_document(cls, doc: Document) -> "Memory":
        metadata = doc.metadata.copy()
        scope = metadata.pop("scope", None)
        if scope is None:
            memory_type = metadata.pop("memory_type", "persistent")
            scope = "session" if memory_type == "session" else "project"
        return cls(
            id=doc.id or str(uuid.uuid4()),
            content=doc.page_content,
            category=metadata.pop("category", "general"),
            scope=scope,
            importance=metadata.pop("importance", 1.0),
            user_id=metadata.pop("user_id", None),
            project_id=metadata.pop("project_id", None),
            session_id=metadata.pop("session_id", None),
            source=metadata.pop("source", "agent"),
            access_count=metadata.pop("access_count", 0),
            created_at=metadata.pop("created_at", time.time()),
            updated_at=metadata.pop("updated_at", time.time()),
            last_accessed_at=metadata.pop("last_accessed_at", None),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "scope": self.scope,
            "importance": self.importance,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "metadata": self.metadata,
            "source": self.source,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        if "memory_type" in data and "scope" not in data:
            memory_type = data.pop("memory_type")
            data["scope"] = "session" if memory_type == "session" else "project"
        return cls(**data)
