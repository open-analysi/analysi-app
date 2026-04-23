"""Knowledge Unit schemas for API requests and responses."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KUBase(BaseModel):
    """Base schema for Knowledge Unit with common Component fields."""

    # Component fields
    name: str = Field(..., min_length=1, max_length=255, description="KU name")
    description: str | None = Field(None, description="KU description")
    version: str = Field(default="1.0.0", description="KU version")
    status: str = Field(default="enabled", description="KU status (enabled/disabled)")
    visible: bool = Field(default=False, description="Whether KU is visible to users")
    system_only: bool = Field(
        default=False, description="Whether KU can only be modified by system"
    )
    app: str = Field(default="default", description="App namespace")
    categories: list[str] = Field(
        default_factory=list, description="KU categories/tags"
    )
    namespace: str = Field(
        default="/", description="Namespace path for scoping (e.g. /skill_name/)"
    )
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts (auto-generated if not provided)",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )


class TableKUCreate(KUBase):
    """Schema for creating a Table Knowledge Unit."""

    table_schema: Annotated[
        dict[str, Any] | None,
        Field(alias="schema", description="Table schema definition"),
    ] = None
    content: dict[str, Any] = Field(
        default_factory=dict, description="Table content as JSONB"
    )
    row_count: int | None = Field(None, ge=0, description="Number of rows")
    column_count: int | None = Field(None, ge=0, description="Number of columns")
    file_path: str | None = Field(None, description="Source file path")


class DocumentKUCreate(KUBase):
    """Schema for creating a Document Knowledge Unit."""

    content: str | None = Field(None, description="Document content")
    markdown_content: str | None = Field(None, description="Markdown representation")
    doc_format: str | None = Field(None, description="Document format (raw/normalized)")
    document_type: str | None = Field(
        None, description="Type (pdf/markdown/html/plaintext)"
    )
    source_url: str | None = Field(None, description="Source URL if applicable")
    file_path: str | None = Field(None, description="Source file path")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class IndexKUCreate(KUBase):
    """Schema for creating an Index Knowledge Unit (management only)."""

    index_type: Literal["vector", "fulltext", "hybrid"] = Field(
        "vector", description="Type of index"
    )
    vector_database: str | None = Field(
        None, description="Vector DB backend (e.g., pgvector)"
    )
    embedding_model: str | None = Field(None, description="Embedding model name")
    # Project Paros: embedding dimensions and backend type
    embedding_dimensions: int | None = Field(
        None, ge=1, description="Embedding vector dimensions (e.g., 1536 for OpenAI)"
    )
    backend_type: str = Field(
        "pgvector", description="Index backend implementation (default: pgvector)"
    )
    chunking_config: dict[str, Any] | None = Field(
        None, description="Chunking configuration"
    )


class KUUpdate(BaseModel):
    """Schema for updating an existing Knowledge Unit."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    namespace: str | None = Field(None, description="Namespace path for scoping")
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )


class TableKUUpdate(KUUpdate):
    """Schema for updating a Table Knowledge Unit."""

    table_schema: Annotated[dict[str, Any] | None, Field(alias="schema")] = None
    content: dict[str, Any] | None = None
    row_count: int | None = Field(None, ge=0)
    column_count: int | None = Field(None, ge=0)
    file_path: str | None = None


class DocumentKUUpdate(KUUpdate):
    """Schema for updating a Document Knowledge Unit."""

    content: str | None = None
    markdown_content: str | None = None
    doc_format: str | None = None
    document_type: str | None = None
    source_url: str | None = None
    file_path: str | None = None
    metadata: dict[str, Any] | None = None


class IndexKUUpdate(KUUpdate):
    """Schema for updating an Index Knowledge Unit."""

    index_type: Literal["vector", "fulltext", "hybrid"] | None = None
    vector_database: str | None = None
    embedding_model: str | None = None
    # Project Paros: embedding dimensions and backend type
    embedding_dimensions: int | None = None
    backend_type: str | None = None
    chunking_config: dict[str, Any] | None = None
    build_status: str | None = None


class KUResponse(KUBase):
    """Base schema for Knowledge Unit response with flattened Component fields."""

    id: UUID
    tenant_id: str
    ku_type: str
    created_by: UUID | None = Field(
        default=None, description="UUID of user who created this KU"
    )
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TableKUResponse(KUResponse):
    """Response schema for Table Knowledge Unit."""

    ku_type: Literal["table"]
    table_schema: dict[str, Any] = Field(serialization_alias="schema")
    content: dict[str, Any]
    row_count: int | None = None
    column_count: int | None = None
    file_path: str | None


class DocumentKUResponse(KUResponse):
    """Response schema for Document Knowledge Unit."""

    ku_type: Literal["document"]
    content: str | None
    markdown_content: str | None
    doc_format: str | None
    document_type: str | None
    source_url: str | None
    file_path: str | None
    metadata: dict[str, Any]
    word_count: int
    character_count: int
    page_count: int
    language: str | None


class IndexKUResponse(KUResponse):
    """Response schema for Index Knowledge Unit."""

    ku_type: Literal["index"]
    index_type: str
    vector_database: str | None
    embedding_model: str | None
    # Project Paros: embedding dimensions and backend type
    embedding_dimensions: int | None = None
    backend_type: str = "pgvector"
    chunking_config: dict[str, Any]
    build_status: str
    build_started_at: datetime | None
    build_completed_at: datetime | None
    build_error_message: str | None
    index_stats: dict[str, Any]
    last_sync_at: datetime | None
