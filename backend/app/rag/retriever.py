import json
from pathlib import Path
from typing import Dict, List

import numpy as np

from app.rag.embedder import EmbeddingService


class LocalVectorRetriever:
    def __init__(
        self,
        index_file: Path,
    ):
        if not index_file.exists():
            raise FileNotFoundError(
                f"Vector index not found: {index_file}"
            )

        self.records = json.loads(
            index_file.read_text(
                encoding="utf-8"
            )
        )

        if not self.records:
            raise RuntimeError(
                "Vector index is empty."
            )

        self.matrix = np.asarray(
            [
                record["embedding"]
                for record in self.records
            ],
            dtype=np.float32,
        )

        self.norms = np.linalg.norm(
            self.matrix,
            axis=1,
        )

        self.embedding_service = (
            EmbeddingService()
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        max_chunks_per_url: int = 2,
    ) -> List[Dict]:

        query_embedding = (
            self.embedding_service.embed_query(
                query
            )
        )

        query_vector = np.asarray(
            query_embedding,
            dtype=np.float32,
        )

        query_norm = np.linalg.norm(
            query_vector
        )

        if query_norm == 0:
            return []

        denominator = (
            self.norms * query_norm
        )

        denominator = np.where(
            denominator == 0,
            1e-8,
            denominator,
        )

        scores = (
            self.matrix @ query_vector
        ) / denominator

        # Fetch more candidates than needed
        candidate_count = min(
            len(self.records),
            top_k * 5,
        )

        candidate_indices = np.argsort(
            scores
        )[::-1][:candidate_count]

        results = []
        url_counts = {}

        for index in candidate_indices:
            record = self.records[int(index)]
            url = record["url"]

            count = url_counts.get(url, 0)

            if count >= max_chunks_per_url:
                continue

            result = {
                key: value
                for key, value in record.items()
                if key != "embedding"
            }

            result["score"] = float(
                scores[index]
            )

            results.append(result)

            url_counts[url] = count + 1

            if len(results) >= top_k:
                break

        return results