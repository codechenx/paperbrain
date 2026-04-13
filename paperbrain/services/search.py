import math
from typing import Protocol


def hybrid_score(keyword_rank: float, vector_rank: float, alpha: float = 0.6) -> float:
    return round(alpha * keyword_rank + (1.0 - alpha) * vector_rank, 2)


QUERY_VECTOR_DIMENSIONS = 1536


def _validate_query_vector(query_vector: list[float]) -> list[float]:
    if len(query_vector) != QUERY_VECTOR_DIMENSIONS:
        raise ValueError(f"query vector must contain exactly {QUERY_VECTOR_DIMENSIONS} values")

    normalized: list[float] = []
    for value in query_vector:
        if isinstance(value, bool):
            raise ValueError("query vector must contain only finite float values")
        try:
            normalized_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("query vector must contain only finite float values") from exc
        if not math.isfinite(normalized_value):
            raise ValueError("query vector must contain only finite float values")
        normalized.append(normalized_value)

    return normalized


class SearchEmbedder(Protocol):
    def embed(self, chunks: list[str]) -> list[list[float]]:
        ...


class SearchRepository(Protocol):
    def browse(self, keyword: str, card_type: str) -> list[dict]:
        ...

    def search_hybrid(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        ...

    def fetch_related_cards(self, paper_slugs: list[str]) -> dict[str, list[dict]]:
        ...


class SearchService:
    def __init__(self, *, repo: SearchRepository, embedder: SearchEmbedder | None = None) -> None:
        self.repo = repo
        self.embedder = embedder

    def browse(self, keyword: str, card_type: str = "all") -> list[dict]:
        return self.repo.browse(keyword, card_type)

    def search(self, query: str, top_k: int = 10, include_cards: bool = False) -> list[dict]:
        if self.embedder is None:
            raise RuntimeError("SearchService requires an embedder for openai-full hybrid search")

        query_embeddings = self.embedder.embed([query])
        if not query_embeddings:
            raise ValueError("embedder returned no query vectors")
        query_vector = _validate_query_vector(query_embeddings[0])

        rows = self.repo.search_hybrid(query, query_vector, top_k)
        paper_slugs = [row["paper_slug"] for row in rows]
        related = self.repo.fetch_related_cards(paper_slugs) if include_cards and paper_slugs else {}
        output: list[dict] = []
        for row in rows:
            enriched = dict(row)
            enriched["score"] = hybrid_score(row["keyword_rank"], row["vector_rank"])
            if include_cards:
                enriched["cards"] = related.get(row["paper_slug"], [])
            output.append(enriched)
        return output
