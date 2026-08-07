from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    url: str
    title: str
    content_type: str
    category: Optional[str] = None
    service_name: Optional[str] = None
    content: str
    include_in_rag: bool = True


class KnowledgeChunk(BaseModel):
    id: str
    url: str
    title: str
    content_type: str
    category: Optional[str] = None
    service_name: Optional[str] = None
    chunk_index: int
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)