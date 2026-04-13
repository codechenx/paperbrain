from collections.abc import Sequence
from typing import Any

from paperbrain.repositories.postgres import PostgresRepo
from paperbrain.services.search import SearchService, hybrid_score


class FakeSearchRepo:
    def __init__(self) -> None:
        self.browse_calls: list[tuple[str, str]] = []
        self.search_calls: list[tuple[str, int]] = []
        self.related_calls: list[list[str]] = []

    def browse(self, keyword: str, card_type: str) -> list[dict]:
        self.browse_calls.append((keyword, card_type))
        return [{"slug": "papers/a", "type": card_type, "text": keyword}]

    def search_hybrid(self, query: str, top_k: int) -> list[dict]:
        self.search_calls.append((query, top_k))
        return [{"paper_slug": "papers/a", "keyword_rank": 0.8, "vector_rank": 0.2}][:top_k]

    def fetch_related_cards(self, paper_slugs: list[str]) -> dict[str, list[dict]]:
        self.related_calls.append(paper_slugs)
        return {paper_slugs[0]: [{"slug": "people/alice", "type": "person"}]}


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.connection.executed.append((sql, params))

    def fetchone(self) -> tuple[Any, ...] | None:
        if self.connection.row_sequence:
            return self.connection.row_sequence.pop(0)
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self.connection.rows_sequence:
            return list(self.connection.rows_sequence.pop(0))
        return []


class FakeConnection:
    def __init__(
        self,
        *,
        row_sequence: list[tuple[Any, ...] | None] | None = None,
        rows_sequence: list[list[tuple[Any, ...]]] | None = None,
    ) -> None:
        self.executed: list[tuple[str, Sequence[Any] | None]] = []
        self.row_sequence = list(row_sequence or [])
        self.rows_sequence = list(rows_sequence or [])

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_hybrid_score_blends_keyword_and_vector() -> None:
    assert hybrid_score(keyword_rank=0.8, vector_rank=0.2, alpha=0.6) == 0.56


def test_browse_delegates_to_repository() -> None:
    repo = FakeSearchRepo()
    service = SearchService(repo=repo)

    rows = service.browse("p53", card_type="topic")

    assert rows == [{"slug": "papers/a", "type": "topic", "text": "p53"}]
    assert repo.browse_calls == [("p53", "topic")]


def test_search_include_cards_appends_related_cards() -> None:
    repo = FakeSearchRepo()
    service = SearchService(repo=repo)

    rows = service.search("p53", top_k=1, include_cards=True)

    assert repo.search_calls == [("p53", 1)]
    assert repo.related_calls == [["papers/a"]]
    assert rows[0]["score"] == 0.56
    assert rows[0]["cards"][0]["slug"] == "people/alice"


def test_search_without_include_cards_skips_related_lookup() -> None:
    repo = FakeSearchRepo()
    service = SearchService(repo=repo)

    rows = service.search("p53", top_k=1, include_cards=False)

    assert repo.search_calls == [("p53", 1)]
    assert repo.related_calls == []
    assert "cards" not in rows[0]


def test_postgres_browse_reads_persisted_cards() -> None:
    connection = FakeConnection(
        rows_sequence=[
            [
                ("papers/a", "paper", '{"title":"A Study"}'),
                ("people/alice", "person", '{"focus_area":"Cancer"}'),
            ]
        ]
    )
    repo = PostgresRepo(connection)

    rows = repo.browse("a", "all")

    assert rows == [
        {"title": "A Study", "slug": "papers/a", "type": "paper"},
        {"focus_area": "Cancer", "slug": "people/alice", "type": "person"},
    ]
    assert len(connection.executed) == 1


def test_postgres_search_hybrid_returns_ranked_rows() -> None:
    connection = FakeConnection(rows_sequence=[[('papers/a', 0.8, 0.2)]])
    repo = PostgresRepo(connection)

    rows = repo.search_hybrid("p53 mutation", top_k=3)

    assert rows == [{"paper_slug": "papers/a", "keyword_rank": 0.8, "vector_rank": 0.2}]
    assert connection.executed[0][1] == ("p53 mutation", "p53 mutation", 3)


def test_postgres_fetch_related_cards_groups_by_paper_slug() -> None:
    connection = FakeConnection(
        rows_sequence=[
            [
                ("papers/a", "papers/a", "paper", '{"title":"A Study"}'),
                ("papers/a", "people/alice", "person", '{"focus_area":"Cancer"}'),
                ("papers/b", "topics/genetics", "topic", '{"topic":"Genetics"}'),
            ]
        ]
    )
    repo = PostgresRepo(connection)

    related = repo.fetch_related_cards(["papers/a", "papers/b"])

    assert related == {
        "papers/a": [
            {"title": "A Study", "slug": "papers/a", "type": "paper"},
            {"focus_area": "Cancer", "slug": "people/alice", "type": "person"},
        ],
        "papers/b": [{"topic": "Genetics", "slug": "topics/genetics", "type": "topic"}],
    }
