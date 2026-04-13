from paperbrain.services.search import SearchService, hybrid_score


class FakeSearchRepo:
    def browse(self, keyword: str, card_type: str) -> list[dict]:
        return [{"slug": "papers/a", "type": card_type, "text": keyword}]

    def search_hybrid(self, query: str, top_k: int) -> list[dict]:
        return [{"paper_slug": "papers/a", "keyword_rank": 0.8, "vector_rank": 0.2}][:top_k]

    def fetch_related_cards(self, paper_slugs: list[str]) -> dict[str, list[dict]]:
        return {paper_slugs[0]: [{"slug": "people/alice", "type": "person"}]}


def test_hybrid_score_blends_keyword_and_vector() -> None:
    assert hybrid_score(keyword_rank=0.8, vector_rank=0.2, alpha=0.6) == 0.56


def test_search_include_cards_appends_related_cards() -> None:
    service = SearchService(repo=FakeSearchRepo())
    rows = service.search("p53", top_k=1, include_cards=True)
    assert rows[0]["score"] == 0.56
    assert rows[0]["cards"][0]["slug"] == "people/alice"

