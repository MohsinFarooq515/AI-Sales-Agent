import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.crawler.crawler import WebsiteCrawler
from app.db.database import SessionLocal
from app.db.models import IntegrationSettingDB
from app.rag.embedder import EmbeddingService
from app.rag.processor import build_chunks, classify_page
from app.rag.retriever import LocalVectorRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "website_pages.json"
DOCUMENTS_FILE = PROJECT_ROOT / "data" / "processed" / "knowledge_documents.json"
CHUNKS_FILE = PROJECT_ROOT / "data" / "processed" / "knowledge_chunks.json"
INDEX_FILE = PROJECT_ROOT / "data" / "processed" / "knowledge_embeddings.json"
WEBSITE_URL = "https://systematicitsolutions.com/"
_lock = asyncio.Lock()


def content_fingerprint(pages):
    return sorted((page.get("canonical_url") or page.get("url"), page.get("content_hash"),
                   page.get("title"), page.get("meta_description"))
                  for page in pages)


def _save_setting(key, value):
    db = SessionLocal()
    try:
        record = db.get(IntegrationSettingDB, key)
        if record:
            record.value = value
        else:
            db.add(IntegrationSettingDB(key=key, value=value))
        db.commit()
    finally:
        db.close()


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _build_index(chunks):
    service = EmbeddingService()
    embeddings = service.embed_texts([chunk["content"] for chunk in chunks])
    return [dict(chunk, embedding=embedding, embedding_model=service.model)
            for chunk, embedding in zip(chunks, embeddings)]


async def refresh_knowledge(sales_agent):
    async with _lock:
        _save_setting("knowledge_refresh_status", "running")
        try:
            crawler = WebsiteCrawler(start_url=WEBSITE_URL, max_pages=100, request_delay=0.25)
            crawled = await crawler.crawl()
            pages = [page.model_dump() for page in crawled]
            if not pages:
                raise RuntimeError("Website crawl returned no pages; existing knowledge was preserved")
            previous = json.loads(RAW_FILE.read_text(encoding="utf-8")) if RAW_FILE.exists() else []
            changed = content_fingerprint(pages) != content_fingerprint(previous)
            if changed or not INDEX_FILE.exists():
                documents = [classify_page(page) for page in pages]
                chunks = [chunk for document in documents for chunk in build_chunks(document)]
                chunk_data = [chunk.model_dump() for chunk in chunks]
                if not chunk_data:
                    raise RuntimeError("Knowledge processing returned no chunks; existing index was preserved")
                index = await asyncio.to_thread(_build_index, chunk_data)
                if not index:
                    raise RuntimeError("Embedding generation returned no records; existing index was preserved")
                _write_json(RAW_FILE, pages)
                _write_json(DOCUMENTS_FILE, [document.model_dump() for document in documents])
                _write_json(CHUNKS_FILE, chunk_data)
                _write_json(INDEX_FILE, index)
                sales_agent.retriever = LocalVectorRetriever(INDEX_FILE)
            _save_setting("knowledge_refresh_status", "updated" if changed else "unchanged")
            _save_setting("knowledge_refresh_at", datetime.utcnow().isoformat())
        except Exception as exc:
            _save_setting("knowledge_refresh_status", "failed")
            _save_setting("knowledge_refresh_error", str(exc)[:1000])
