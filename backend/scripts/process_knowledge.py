import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.rag.processor import (
    build_chunks,
    classify_page,
)


INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "website_pages.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

DOCUMENTS_FILE = (
    OUTPUT_DIR
    / "knowledge_documents.json"
)

CHUNKS_FILE = (
    OUTPUT_DIR
    / "knowledge_chunks.json"
)


def main():

    pages = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )

    documents = [
        classify_page(page)
        for page in pages
    ]

    chunks = []

    for document in documents:
        chunks.extend(
            build_chunks(document)
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DOCUMENTS_FILE.write_text(
        json.dumps(
            [
                document.model_dump()
                for document in documents
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    CHUNKS_FILE.write_text(
        json.dumps(
            [
                chunk.model_dump()
                for chunk in chunks
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    included = sum(
        1
        for document in documents
        if document.include_in_rag
    )

    excluded = (
        len(documents)
        - included
    )

    print()
    print("=" * 60)
    print("KNOWLEDGE PROCESSING COMPLETE")
    print("=" * 60)

    print(
        f"Pages read: {len(pages)}"
    )

    print(
        f"Documents included: {included}"
    )

    print(
        f"Documents excluded: {excluded}"
    )

    print(
        f"Chunks generated: {len(chunks)}"
    )

    print()
    print(
        f"Documents: {DOCUMENTS_FILE}"
    )

    print(
        f"Chunks: {CHUNKS_FILE}"
    )


if __name__ == "__main__":
    main()