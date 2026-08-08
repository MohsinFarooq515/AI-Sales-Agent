import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.rag.retriever import LocalVectorRetriever


INDEX_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_embeddings.json"
)


TEST_QUERIES = [
    (
        "I own a dental clinic and want more "
        "customers near my location."
    ),
    (
        "I want to advertise my business "
        "on Google and generate leads."
    ),
    (
        "I need an online Shopify store "
        "for my business."
    ),
    (
        "My website has indexing and "
        "technical SEO problems."
    ),
]


def main():

    retriever = LocalVectorRetriever(
        INDEX_FILE
    )

    for query in TEST_QUERIES:

        print()
        print("=" * 80)
        print(f"QUERY: {query}")
        print("=" * 80)

        results = retriever.search(
            query=query,
            top_k=3,
        )

        for position, result in enumerate(
            results,
            start=1,
        ):
            print()
            print(
                f"{position}. "
                f"{result['title']}"
            )

            print(
                f"   Score: "
                f"{result['score']:.4f}"
            )

            print(
                f"   Type: "
                f"{result['content_type']}"
            )

            print(
                f"   URL: "
                f"{result['url']}"
            )

            preview = (
                result["content"]
                .replace("\n", " ")
                [:250]
            )

            print(
                f"   Preview: {preview}"
            )


if __name__ == "__main__":
    main()