from pydantic import BaseModel, Field


class CrawledPage(BaseModel):
    url: str
    canonical_url: str
    title: str = ""
    meta_description: str = ""
    content: str
    content_hash: str
    links: list[str] = Field(default_factory=list)
    status_code: int = 200