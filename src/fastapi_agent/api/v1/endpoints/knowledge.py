"""Knowledge base management API endpoints."""

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from fastapi_agent.rag.rag_service import rag_service

router = APIRouter()


class DocumentResponse(BaseModel):
    """Document response model."""

    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int


class DocumentListResponse(BaseModel):
    """Document list response model."""

    documents: list[dict[str, Any]]
    total: int


class SearchRequest(BaseModel):
    """Search request model."""

    query: str
    top_k: int = 5
    mode: str = "hybrid"  # "hybrid", "semantic", or "keyword"
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3


class SearchResult(BaseModel):
    """Search result model."""

    id: str
    content: str
    filename: str
    similarity: float


class SearchResponse(BaseModel):
    """Search response model."""

    results: list[SearchResult]
    total: int


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    """Upload a document to the knowledge base.

    Supported formats: TXT, Markdown, PDF
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Check file type
    if not rag_service.processor.is_supported(file.filename):
        supported = list(rag_service.processor.SUPPORTED_TYPES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {supported}",
        )

    try:
        # Get file size
        content = await file.read()
        file_size = len(content)

        # Reset file position for processing
        await file.seek(0)

        # Add document to knowledge base
        result = await rag_service.add_document(
            file=file.file,
            filename=file.filename,
            file_size=file_size,
        )

        return DocumentResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document: {str(e)}",
        )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """List all documents in the knowledge base."""
    documents = await rag_service.list_documents()
    return DocumentListResponse(documents=documents, total=len(documents))


@router.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict[str, Any]:
    """Get document details by ID."""
    document = await rag_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict[str, str]:
    """Delete a document from the knowledge base."""
    success = await rag_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted successfully"}


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest) -> SearchResponse:
    """Search the knowledge base for relevant content.

    Modes:
    - hybrid (default): Combines semantic and keyword search using RRF
    - semantic: Pure vector similarity search
    - keyword: Pure full-text search (BM25-like)
    """
    try:
        results = await rag_service.search(
            query=request.query,
            top_k=request.top_k,
            mode=request.mode,
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
        )

        search_results = [
            SearchResult(
                id=r["id"],
                content=r["content"],
                filename=r["filename"],
                similarity=r["similarity"],
            )
            for r in results
        ]

        return SearchResponse(results=search_results, total=len(search_results))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )
