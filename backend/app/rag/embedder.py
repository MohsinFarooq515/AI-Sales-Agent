import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI

BACKEND_DIR = Path(__file__).resolve().parents[2]

# The backend .env is authoritative. This prevents a stale key exported by
# Bash/PowerShell from silently overriding the key configured for this app.
load_dotenv(BACKEND_DIR / ".env", override=True)


class EmbeddingService:
    def __init__(
        self,
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
                "OPENAI_EMBEDDING_MODEL",
                "text-embedding-3-small",
            )
        )

        self.client = OpenAI(
            api_key=api_key
        )

    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 50,
    ) -> List[List[float]]:

        if not texts:
            return []

        embeddings = []

        for start in range(
            0,
            len(texts),
            batch_size,
        ):
            batch = texts[
                start:start + batch_size
            ]

            response = (
                self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                )
            )

            ordered = sorted(
                response.data,
                key=lambda item: item.index,
            )

            embeddings.extend(
                [
                    item.embedding
                    for item in ordered
                ]
            )

        return embeddings

    def embed_query(
        self,
        query: str,
    ) -> List[float]:

        results = self.embed_texts(
            [query],
            batch_size=1,
        )

        return results[0]
