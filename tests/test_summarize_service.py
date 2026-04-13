from dataclasses import dataclass
from typing import Any

import pytest

from paperbrain.repositories.postgres import PostgresRepo
from paperbrain.services.summarize import SummarizeService


@dataclass
class FakePaper:
    slug: str
    title: str
    journal: str
    year: int
    authors: list[str]
    corresponding_authors: list[str]
    full_text: str


class FakeRepo:
    def __init__(self) -> None:
        self.force_all_seen: bool | None = None
        self.paper_cards: list[dict] = []
        self.person_cards: list[dict] = []
        self.topic_cards: list[dict] = []
        self.calls: list[str] = []

    def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
        self.force_all_seen = force_all
        return [
            FakePaper(
                slug="papers/chen-p53-nature-2024-abc123",
                title="P53 Mutations and Cancer Progression",
                journal="Nature",
                year=2024,
                authors=["Stephen Chen"],
                corresponding_authors=["Alice Research <alice@university.org>"],
                full_text="P53 mutation study",
            ),
            FakePaper(
                slug="papers/lee-immunity-cell-2023-def456",
                title="Cellular Immunity Dynamics",
                journal="Cell",
                year=2023,
                authors=["Soo Lee"],
                corresponding_authors=["Soo Lee <soo@institute.org>"],
                full_text="Immunity response study",
            ),
        ]

    def upsert_paper_card(self, card: dict) -> None:
        self.calls.append("paper")
        self.paper_cards.append(card)

    def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        _ = replace_existing
        self.calls.append("person")
        self.person_cards = cards

    def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        _ = replace_existing
        self.calls.append("topic")
        self.topic_cards = cards


class FakeLLM:
    def __init__(self) -> None:
        self.person_input: list[dict] | None = None
        self.topic_input: list[dict] | None = None

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        _ = paper_text
        return {
            "slug": metadata["slug"],
            "type": "article",
            "title": metadata["title"],
            "summary": "x",
            "corresponding_authors": metadata["corresponding_authors"],
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        self.person_input = list(paper_cards)
        return [
            {
                "slug": "people/alice-university-org",
                "type": "person",
                "related_papers": [paper_cards[0]["slug"]],
            },
            {
                "slug": "people/soo-institute-org",
                "type": "person",
                "related_papers": [paper_cards[1]["slug"]],
            },
        ]

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        self.topic_input = list(person_cards)
        return [
            {
                "slug": "topics/cancer-genetics",
                "type": "topic",
                "related_people": [card["slug"] for card in person_cards],
                "related_papers": ["papers/chen-p53-nature-2024-abc123"],
            }
        ]


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.connection.executed.append((sql, params))

    def fetchone(self) -> tuple[Any, ...] | None:
        if self.connection.row_sequence:
            return self.connection.row_sequence.pop(0)
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self.connection.rows_sequence:
            return list(self.connection.rows_sequence.pop(0))
        return []


class FakeTransaction:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> None:
        self.connection.transaction_entered += 1

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.connection.transaction_exited += 1


class FakeConnection:
    def __init__(
        self,
        *,
        rows_sequence: list[list[tuple[Any, ...]]] | None = None,
        row_sequence: list[tuple[Any, ...] | None] | None = None,
    ) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.rows_sequence = list(rows_sequence or [])
        self.row_sequence = list(row_sequence or [])
        self.transaction_entered = 0
        self.transaction_exited = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


def test_summarize_persists_cards_and_returns_counts() -> None:
    repo = FakeRepo()
    llm = FakeLLM()
    service = SummarizeService(repo=repo, llm=llm)

    result = service.run(force_all=False)

    assert repo.force_all_seen is False
    assert repo.calls == ["paper", "paper", "person", "topic"]
    assert llm.person_input == repo.paper_cards
    assert llm.topic_input == repo.person_cards
    assert [card["slug"] for card in repo.paper_cards] == [
        "papers/chen-p53-nature-2024-abc123",
        "papers/lee-immunity-cell-2023-def456",
    ]
    assert result.paper_cards == 2
    assert result.person_cards == 2
    assert result.topic_cards == 1


def test_summarize_generates_person_topic_when_corresponding_authors_inferred() -> None:
    class MissingAuthorRepo(FakeRepo):
        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            self.force_all_seen = force_all
            return [
                FakePaper(
                    slug="papers/missing-author",
                    title="Missing Author Paper",
                    journal="Nature",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=[],
                    full_text="first-page text with email: inferred@example.org",
                )
            ]

    class InferenceLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": ["inferred@example.org"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            assert paper_cards[0]["corresponding_authors"] == ["inferred@example.org"]
            return [
                {
                    "slug": "people/inferred-example-org",
                    "type": "person",
                    "focus_area": "Inference",
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/inference",
                    "type": "topic",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": ["papers/missing-author"],
                }
            ]

    repo = MissingAuthorRepo()
    llm = InferenceLLM()
    result = SummarizeService(repo=repo, llm=llm).run(force_all=True)

    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1


def test_postgres_list_papers_for_summary_decodes_json_columns() -> None:
    connection = FakeConnection(
        rows_sequence=[
            [
                (
                    "paper-1",
                    "papers/chen-p53-nature-2024-abc123",
                    "P53 Mutations and Cancer Progression",
                    "Nature",
                    2024,
                    '["Stephen Chen"]',
                    '["Alice Research <alice@university.org>"]',
                    "P53 mutation study",
                )
            ]
        ]
    )
    repo = PostgresRepo(connection)

    papers = repo.list_papers_for_summary(force_all=False)

    assert len(papers) == 1
    assert papers[0].slug == "papers/chen-p53-nature-2024-abc123"
    assert papers[0].authors == ["Stephen Chen"]
    assert papers[0].corresponding_authors == ["Alice Research <alice@university.org>"]
    assert "LEFT JOIN paper_cards" in connection.executed[0][0]


def test_postgres_upsert_paper_card_raises_for_unknown_paper_slug() -> None:
    connection = FakeConnection(row_sequence=[None])
    repo = PostgresRepo(connection)

    with pytest.raises(ValueError, match=r"Unknown paper slug"):
        repo.upsert_paper_card({"slug": "papers/missing", "type": "article", "summary": "x"})


def test_postgres_persists_person_and_topic_links() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.upsert_person_cards(
        [
            {
                "slug": "people/alice-university-org",
                "type": "person",
                "related_papers": ["papers/a", "papers/b"],
            }
        ]
    )
    repo.upsert_topic_cards(
        [
            {
                "slug": "topics/cancer-genetics",
                "type": "topic",
                "related_papers": ["papers/a"],
                "related_people": ["people/alice-university-org"],
            }
        ]
    )

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "INSERT INTO person_cards" in executed_sql
    assert "INSERT INTO paper_person_links" in executed_sql
    assert "INSERT INTO topic_cards" in executed_sql
    assert "INSERT INTO paper_topic_links" in executed_sql
    assert "INSERT INTO person_topic_links" in executed_sql
    assert connection.transaction_entered == 2
    assert connection.transaction_exited == 2


def test_summarize_does_not_delete_existing_links_when_derived_cards_omit_relations() -> None:
    connection = FakeConnection(
        rows_sequence=[
            [
                (
                    "paper-1",
                    "papers/chen-p53-nature-2024-abc123",
                    "P53 Mutations and Cancer Progression",
                    "Nature",
                    2024,
                    '["Stephen Chen"]',
                    '["Alice Research <alice@university.org>"]',
                    "P53 mutation study",
                )
            ]
        ],
        row_sequence=[("papers/chen-p53-nature-2024-abc123",)],
    )
    repo = PostgresRepo(connection)

    class SparseLLM:
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            return [{"slug": "people/alice-university-org", "type": "person", "focus_area": "Cancer genomics"}]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            return [{"slug": "topics/cancer-genomics", "type": "topic", "topic": "Cancer Genomics"}]

    result = SummarizeService(repo=repo, llm=SparseLLM()).run(force_all=False)

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "DELETE FROM paper_person_links" not in executed_sql
    assert "DELETE FROM paper_topic_links" not in executed_sql
    assert "DELETE FROM person_topic_links" not in executed_sql
    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1
