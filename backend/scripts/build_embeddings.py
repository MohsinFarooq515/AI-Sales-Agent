import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.rag.embedder import EmbeddingService


INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_chunks.json"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_embeddings.json"
)


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Knowledge chunks not found: {INPUT_FILE}"
        )

    chunks = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )

    print()
    print("=" * 60)
    print("BUILDING EMBEDDING INDEX")
    print("=" * 60)

    print(
        f"Chunks: {len(chunks)}"
    )

    service = EmbeddingService()

    print(
        f"Model: {service.model}"
    )

    texts = [
        chunk["content"]
        for chunk in chunks
    ]

    print()
    print("Generating embeddings...")

    embeddings = service.embed_texts(
        texts
    )

    if len(embeddings) != len(chunks):
        raise RuntimeError(
            "Embedding count does not match chunk count."
        )

    records = []

    for chunk, embedding in zip(
        chunks,
        embeddings,
    ):
        record = dict(chunk)

        record["embedding"] = embedding
        record["embedding_model"] = (
            service.model
        )

        records.append(record)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dimensions = (
        len(embeddings[0])
        if embeddings
        else 0
    )

    print()
    print("=" * 60)
    print("EMBEDDING INDEX COMPLETE")
    print("=" * 60)

    print(
        f"Embeddings generated: {len(embeddings)}"
    )

    print(
        f"Vector dimensions: {dimensions}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()