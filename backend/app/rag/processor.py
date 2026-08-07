from typing import List
import hashlib
import re
from urllib.parse import urlparse

from app.rag.models import KnowledgeChunk, KnowledgeDocument


CATEGORY_ROOTS = {
    "seo": "SEO",
    "advertisements": "Advertisements",
    "development": "Development",
    "designing": "Designing",
    "marketing": "Marketing",
    "content-writing": "Content Writing",
}


EXCLUDED_PATHS = {
    "/career",
    "/terms-conditions",
}


def clean_title(title: str) -> str:
    title = re.sub(
        r"\s*-\s*Systematic IT Solutions\s*$",
        "",
        title,
        flags=re.I,
    )

    return title.strip()


def classify_page(page: dict) -> KnowledgeDocument:
    url = page["canonical_url"]
    parsed = urlparse(url)

    path = parsed.path.rstrip("/") or "/"
    parts = [
        part
        for part in path.split("/")
        if part
    ]

    title = clean_title(
        page.get("title", "")
    )

    content_type = "other"
    category = None
    service_name = None
    include_in_rag = True

    # -------------------------
    # Explicit exclusions
    # -------------------------

    if path in EXCLUDED_PATHS:
        include_in_rag = False
        content_type = "other"

    # -------------------------
    # Main company pages
    # -------------------------

    elif path == "/":
        content_type = "company"

    elif path == "/about":
        content_type = "company"

    elif path == "/contact":
        content_type = "contact"

    elif path == "/services":
        content_type = "service_overview"

    # -------------------------
    # Service categories/pages
    # -------------------------

    elif parts:
        root = parts[0]

        if root in CATEGORY_ROOTS:
            category = CATEGORY_ROOTS[root]

            if len(parts) == 1:
                content_type = "service_category"

            else:
                content_type = "service"
                service_name = title

    return KnowledgeDocument(
        url=url,
        title=title,
        content_type=content_type,
        category=category,
        service_name=service_name,
        content=page["content"],
        include_in_rag=include_in_rag,
    )


def split_into_chunks(
    text: str,
    max_chars: int = 1400,
    overlap_chars: int = 200,
) -> list[str]:

    if len(text) <= max_chars:
        return [text]

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    chunks: list[str] = []
    current = ""

    for sentence in sentences:

        candidate = (
            f"{current} {sentence}".strip()
        )

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

        # Keep some previous context
        overlap = ""

        if current:
            overlap = current[
                -overlap_chars:
            ].strip()

        current = (
            f"{overlap} {sentence}".strip()
        )

        # Handle unusually long sentence/content
        while len(current) > max_chars:
            chunks.append(
                current[:max_chars]
            )

            current = current[
                max_chars - overlap_chars:
            ].strip()

    if current:
        chunks.append(current)

    return chunks


def build_chunks(
    document: KnowledgeDocument,
) -> list[KnowledgeChunk]:

    if not document.include_in_rag:
        return []

    raw_chunks = split_into_chunks(
        document.content
    )

    chunks: list[KnowledgeChunk] = []

    for index, chunk_text in enumerate(
        raw_chunks
    ):

        # Add context to every chunk
        context_parts = [
            f"Page: {document.title}",
        ]

        if document.category:
            context_parts.append(
                f"Category: {document.category}"
            )

        if document.service_name:
            context_parts.append(
                f"Service: {document.service_name}"
            )

        contextual_content = (
            "\n".join(context_parts)
            + "\n\n"
            + chunk_text
        )

        chunk_id_source = (
            f"{document.url}:{index}:"
            f"{contextual_content}"
        )

        chunk_id = hashlib.sha256(
            chunk_id_source.encode("utf-8")
        ).hexdigest()[:24]

        chunks.append(
            KnowledgeChunk(
                id=chunk_id,
                url=document.url,
                title=document.title,
                content_type=document.content_type,
                category=document.category,
                service_name=document.service_name,
                chunk_index=index,
                content=contextual_content,
                metadata={
                    "source": "website",
                    "company": (
                        "Systematic IT Solutions"
                    ),
                },
            )
        )

    return chunks