import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.rag.generator import RAGService


INDEX_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_embeddings.json"
)


TEST_QUERIES = [
    (
        "I run a dental clinic and I am not "
        "getting enough customers from Google. "
        "What would you recommend?"
    ),
    (
        "Can you help me build a Shopify store "
        "and also bring customers to it?"
    ),
    (
        "My website pages are not getting indexed "
        "properly. What service should I use?"
    ),
]


def main():

    rag = RAGService(
        index_file=INDEX_FILE
    )

    for query in TEST_QUERIES:

        print()
        print("=" * 80)
        print(f"QUESTION: {query}")
        print("=" * 80)

        result = rag.answer(
            query
        )

        print()
        print("ANSWER:")
        print(result["answer"])

        print()
        print("SOURCES:")

        for source in result["sources"]:
            print(
                f"- {source['title']} "
                f"({source['score']:.4f})"
            )
            print(
                f"  {source['url']}"
            )


if __name__ == "__main__":
    main()