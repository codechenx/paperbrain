from typing import Protocol


def hybrid_score(keyword_rank: float, vector_rank: float, alpha: float = 0.6) -> float:
    return round(alpha * keyword_rank + (1.0 - alpha) * vector_rank, 2)


class SearchRepository(Protocol):
    def browse(self, keyword: str, card_type: str) -> list[dict]:
        ...

    def search_hybrid(self, query: str, top_k: int) -> list[dict]:
        ...

    def fetch_related_cards(self, paper_slugs: list[str]) -> dict[str, list[dict]]:
        ...


class SearchService:
    def __init__(self, *, repo: SearchRepository) -> None:
        self.repo = repo

    def browse(self, keyword: str, card_type: str = "all") -> list[dict]:
        return self.repo.browse(keyword, card_type)

    def search(self, query: str, top_k: int = 10, include_cards: bool = False) -> list[dict]:
        rows = self.repo.search_hybrid(query, top_k)
        paper_slugs = [row["paper_slug"] for row in rows]
        related = self.repo.fetch_related_cards(paper_slugs) if include_cards else {}
        output: list[dict] = []
        for row in rows:
            enriched = dict(row)
            enriched["score"] = hybrid_score(row["keyword_rank"], row["vector_rank"])
            if include_cards:
                enriched["cards"] = related.get(row["paper_slug"], [])
            output.append(enriched)
        return output

