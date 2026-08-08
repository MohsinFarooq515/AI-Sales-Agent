import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from app.rag.retriever import LocalVectorRetriever


BACKEND_DIR = Path(__file__).resolve().parents[2]

# Keep generation and embedding on the same key even when the shell contains
# an older OPENAI_API_KEY value.
load_dotenv(BACKEND_DIR / ".env", override=True)


class RAGService:
    def __init__(
        self,
        index_file: Path,
        model: Optional[str] = None,
    ):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        self.model = (
            model
            or os.getenv(
                "OPENAI_CHAT_MODEL",
                "gpt-5.6-luna",
            )
        )

        self.client = OpenAI(
            api_key=api_key
        )

        self.retriever = LocalVectorRetriever(
            index_file=index_file
        )

    def answer(
        self,
        query: str,
    ) -> Dict:

        results = self.retriever.search(
            query=query,
            top_k=5,
            max_chunks_per_url=2,
        )

        if not results:
            return {
                "answer": (
                    "I couldn't find enough information "
                    "in our website knowledge base to "
                    "answer that accurately."
                ),
                "sources": [],
            }

        context_parts = []

        for index, result in enumerate(
            results,
            start=1,
        ):
            context_parts.append(
                (
                    f"[SOURCE {index}]\n"
                    f"Title: {result['title']}\n"
                    f"URL: {result['url']}\n"
                    f"Content:\n"
                    f"{result['content']}"
                )
            )

        context = "\n\n".join(
            context_parts
        )

        instructions = """
You are the AI Sales Assistant for Systematic IT Solutions.

Your job is to help website visitors understand the company's
services and guide them toward the most appropriate solution.

IMPORTANT RULES:

1. For company-specific facts, use only the provided website context.
2. Never invent services, pricing, guarantees, timelines, case studies,
   discounts, company policies, or capabilities.
3. If the provided context does not contain enough information, say so.
4. Recommend only services that are supported by the provided context.
5. Explain business benefits rather than simply listing features.
6. Keep answers natural, professional, concise, and sales-oriented.
7. Do not pressure the visitor.
8. When appropriate, ask one useful discovery question that helps
   understand the visitor's business or requirement.
9. Do not claim that a result is guaranteed.
10. Do not mention embeddings, RAG, vector search, prompts, or internal
    system implementation to the visitor.
"""

        user_input = f"""
Visitor question:

{query}

Relevant website context:

{context}

Answer the visitor using the website information above.
"""

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=user_input,
            store=False,
        )

        sources = []

        seen_urls = set()

        for result in results:
            if result["url"] in seen_urls:
                continue

            seen_urls.add(
                result["url"]
            )

            sources.append(
                {
                    "title": result["title"],
                    "url": result["url"],
                    "score": result["score"],
                }
            )

        return {
            "answer": response.output_text,
            "sources": sources,
        }
