import copy
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
        self._last_topic_person_slugs: list[str] = []

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

    def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
        _ = paper_slugs
        return []

    def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        self._last_topic_person_slugs = list(person_slugs)
        return ["topics/cancer-genetics"] if person_slugs else []

    def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        _ = person_slugs
        return [str(card.get("slug", "")).strip() for card in self.paper_cards if str(card.get("slug", "")).strip()]

    def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
        _ = topic_slugs
        return list(self._last_topic_person_slugs)

    def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
        by_slug = {str(card.get("slug", "")).strip(): copy.deepcopy(card) for card in self.paper_cards}
        return [by_slug[slug] for slug in paper_slugs if slug in by_slug]

    def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
        by_slug = {str(card.get("slug", "")).strip(): copy.deepcopy(card) for card in self.person_cards}
        if by_slug:
            return [by_slug[slug] for slug in person_slugs if slug in by_slug]
        fallback_paper_slug = str(self.paper_cards[0].get("slug", "")).strip() if self.paper_cards else ""
        return [
            {
                "slug": slug,
                "type": "person",
                "related_papers": [fallback_paper_slug] if fallback_paper_slug else [],
            }
            for slug in person_slugs
        ]

    def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        _ = replace_existing
        self.calls.append("person")
        assert all(card.get("focus_area") for card in cards)
        self.person_cards = copy.deepcopy(cards)

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
            "paper_type": "article",
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


def build_summary_paper(slug: str) -> FakePaper:
    return FakePaper(
        slug=slug,
        title=f"Title for {slug}",
        journal="Journal",
        year=2024,
        authors=["Author"],
        corresponding_authors=["Author <author@example.org>"],
        full_text=f"full text for {slug}",
    )


class FakeSummaryRepo:
    def __init__(self) -> None:
        self.papers_for_summary: list[FakePaper] = []
        self.paper_cards_existing: list[dict] = []
        self.paper_cards_upserted: list[dict] = []
        self.person_cards_upserted: list[dict] = []
        self.topic_cards_upserted: list[dict] = []

    def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
        _ = force_all
        upserted_slugs = {str(card.get("slug", "")).strip() for card in self.paper_cards_upserted}
        return [paper for paper in self.papers_for_summary if paper.slug not in upserted_slugs]

    def upsert_paper_card(self, card: dict) -> None:
        self.paper_cards_upserted.append(copy.deepcopy(card))

    def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
        _ = paper_slugs
        return []

    def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        _ = person_slugs
        return []

    def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        _ = person_slugs
        return []

    def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
        _ = topic_slugs
        return []

    def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
        all_cards = self.fetch_all_paper_cards()
        by_slug = {str(card.get("slug", "")).strip(): copy.deepcopy(card) for card in all_cards}
        return [by_slug[slug] for slug in paper_slugs if slug in by_slug]

    def fetch_all_paper_cards(self) -> list[dict]:
        return copy.deepcopy(self.paper_cards_existing + self.paper_cards_upserted)

    def list_all_person_slugs(self) -> list[str]:
        return []

    def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
        _ = person_slugs
        return []

    def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        _ = replace_existing
        self.person_cards_upserted = copy.deepcopy(cards)

    def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        _ = replace_existing
        self.topic_cards_upserted = copy.deepcopy(cards)


class FakeSummaryLLM:
    def __init__(self) -> None:
        self.derive_person_calls = 0
        self.derive_topic_calls = 0
        self.call_order: list[str] = []
        self.person_inputs: list[list[str]] = []

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        _ = paper_text
        return {
            "slug": metadata["slug"],
            "type": "article",
            "paper_type": "article",
            "title": metadata["title"],
            "summary": "summary",
            "corresponding_authors": metadata["corresponding_authors"],
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        self.derive_person_calls += 1
        self.call_order.append("person")
        self.person_inputs.append([str(card.get("slug", "")).strip() for card in paper_cards])
        if not paper_cards:
            return []
        return [
            {
                "slug": f"people/{str(card.get('slug', '')).split('/')[-1]}",
                "type": "person",
                "related_papers": [card["slug"]],
            }
            for card in paper_cards
        ]

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        self.derive_topic_calls += 1
        self.call_order.append("topic")
        if not person_cards:
            return []
        return [
            {
                "slug": "topics/generated-topic",
                "type": "topic",
                "topic": "Generated Topic",
                "related_people": [card["slug"] for card in person_cards],
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

    result = service.run(card_scope=None)

    assert repo.force_all_seen is False
    assert repo.calls == ["paper", "paper", "person", "topic"]
    assert llm.person_input == repo.paper_cards
    assert [card["slug"] for card in llm.topic_input or []] == [card["slug"] for card in repo.person_cards]
    assert all(card["focus_area"] for card in repo.person_cards)
    assert [card["slug"] for card in repo.paper_cards] == [
        "papers/chen-p53-nature-2024-abc123",
        "papers/lee-immunity-cell-2023-def456",
    ]
    assert result.paper_cards == 2
    assert result.person_cards == 2
    assert result.topic_cards == 1


def test_summarize_card_scope_all_maps_to_force_all() -> None:
    repo = FakeRepo()
    llm = FakeLLM()

    result = SummarizeService(repo=repo, llm=llm).run(card_scope="all")

    assert repo.force_all_seen is True
    assert result.paper_cards == 2


def test_summarize_default_skips_person_topic_when_pending_papers_exist() -> None:
    repo = FakeSummaryRepo()
    repo.paper_cards_existing = [{"slug": "papers/existing", "type": "article", "paper_type": "article"}]
    repo.papers_for_summary = [build_summary_paper(slug="papers/new-1"), build_summary_paper(slug="papers/new-2")]
    llm = FakeSummaryLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(limit=1)

    assert stats.paper_cards == 1
    assert stats.person_cards == 0
    assert stats.topic_cards == 0
    assert llm.derive_person_calls == 0
    assert llm.derive_topic_calls == 0


def test_summarize_all_skips_downstream_when_pending_papers_exist() -> None:
    repo = FakeSummaryRepo()
    repo.papers_for_summary = [build_summary_paper(slug="papers/new-1"), build_summary_paper(slug="papers/new-2")]
    llm = FakeSummaryLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(card_scope="all", limit=1)

    assert stats.paper_cards == 1
    assert stats.person_cards == 0
    assert stats.topic_cards == 0
    assert llm.derive_person_calls == 0
    assert llm.derive_topic_calls == 0


def test_summarize_all_runs_person_then_topic_after_papers_complete() -> None:
    repo = FakeSummaryRepo()
    repo.papers_for_summary = []
    repo.paper_cards_existing = [{"slug": "papers/p-1", "type": "article", "paper_type": "article"}]
    llm = FakeSummaryLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(card_scope="all")

    assert stats.paper_cards == 0
    assert stats.person_cards == 1
    assert stats.topic_cards == 1
    assert llm.person_inputs == [["papers/p-1"]]
    assert llm.call_order == ["person", "topic"]


def test_summarize_all_raises_value_error_when_topics_empty_for_existing_people() -> None:
    class AllScopeRepo(FakeRepo):
        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.person_cards = copy.deepcopy(cards)

    class EmptyTopicsLLM(FakeLLM):
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            return []

    repo = AllScopeRepo()
    llm = EmptyTopicsLLM()

    with pytest.raises(ValueError, match=r"No linked topics found for person card"):
        SummarizeService(repo=repo, llm=llm).run(card_scope="all")

    assert repo.person_cards == []
    assert repo.topic_cards == []


def test_summarize_card_scope_paper_rebuilds_papers_only() -> None:
    class PaperOnlyRepo:
        def __init__(self) -> None:
            self.force_all_seen: bool | None = None
            self.paper_cards: list[dict] = []

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            self.force_all_seen = force_all
            return [
                FakePaper(
                    slug="papers/a",
                    title="A",
                    journal="J",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["A <a@example.org>"],
                    full_text="A",
                ),
                FakePaper(
                    slug="papers/b",
                    title="B",
                    journal="J",
                    year=2024,
                    authors=["B"],
                    corresponding_authors=["B <b@example.org>"],
                    full_text="B",
                ),
            ]

        def upsert_paper_card(self, card: dict) -> None:
            self.paper_cards.append(card)

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("person cards must not be upserted for paper scope")

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("topic cards must not be upserted for paper scope")

    class PaperOnlyLLM:
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "article",
                "title": metadata["title"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            raise AssertionError("person derivation must not run for paper scope")

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            raise AssertionError("topic derivation must not run for paper scope")

    repo = PaperOnlyRepo()
    result = SummarizeService(repo=repo, llm=PaperOnlyLLM()).run(card_scope="paper")

    assert repo.force_all_seen is True
    assert [card["slug"] for card in repo.paper_cards] == ["papers/a", "papers/b"]
    assert result.paper_cards == 2
    assert result.person_cards == 0
    assert result.topic_cards == 0


def test_summarize_card_scope_person_rebuilds_people_only_from_article_cards() -> None:
    class PersonOnlyRepo:
        def __init__(self) -> None:
            self.full_paper_fetch_called = False
            self.paper_cards_fetch_count = 0
            self.person_cards: list[dict] = []
            self.replace_existing_flags: list[bool] = []

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            self.full_paper_fetch_called = True
            raise AssertionError("full paper fetch path must not run for person scope")

        def fetch_all_paper_cards(self) -> list[dict]:
            self.paper_cards_fetch_count += 1
            return [
                {"slug": "papers/article-a", "type": "article", "paper_type": "article"},
                {"slug": "papers/review-b", "type": "article", "paper_type": "review"},
            ]

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            self.person_cards = copy.deepcopy(cards)
            self.replace_existing_flags.append(replace_existing)

        def upsert_paper_card(self, card: dict) -> None:
            _ = card
            raise AssertionError("paper cards must not be upserted for person scope")

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("topic cards must not be upserted for person scope")

    class PersonOnlyLLM:
        def __init__(self) -> None:
            self.person_input: list[dict] | None = None

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text, metadata
            raise AssertionError("paper summarization must not run for person scope")

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            self.person_input = list(paper_cards)
            return [
                {
                    "slug": "people/a",
                    "type": "person",
                    "related_papers": ["papers/article-a"],
                    "focus_area": ["Oncology"],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            raise AssertionError("topic derivation must not run for person scope")

    repo = PersonOnlyRepo()
    llm = PersonOnlyLLM()
    result = SummarizeService(repo=repo, llm=llm).run(card_scope="person")

    assert repo.full_paper_fetch_called is False
    assert repo.paper_cards_fetch_count == 1
    assert [card["slug"] for card in llm.person_input or []] == ["papers/article-a"]
    assert repo.replace_existing_flags == [True]
    assert [card["slug"] for card in repo.person_cards] == ["people/a"]
    assert result.paper_cards == 0
    assert result.person_cards == 1
    assert result.topic_cards == 0


def test_summarize_card_scope_person_skips_upsert_when_no_article_source_cards() -> None:
    class PersonScopeEmptySourceRepo:
        def __init__(self) -> None:
            self.upsert_calls = 0
            self.full_paper_fetch_called = False

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            self.full_paper_fetch_called = True
            raise AssertionError("full paper fetch path must not run for person scope")

        def fetch_all_paper_cards(self) -> list[dict]:
            return [{"slug": "papers/review-a", "type": "article", "paper_type": "review"}]

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            self.upsert_calls += 1

    class PersonScopeEmptySourceLLM:
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            assert paper_cards == []
            return []

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text, metadata
            raise AssertionError("paper summarization must not run for person scope")

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            raise AssertionError("topic derivation must not run for person scope")

    repo = PersonScopeEmptySourceRepo()
    result = SummarizeService(repo=repo, llm=PersonScopeEmptySourceLLM()).run(card_scope="person")

    assert repo.full_paper_fetch_called is False
    assert repo.upsert_calls == 0
    assert result.paper_cards == 0
    assert result.person_cards == 0
    assert result.topic_cards == 0


def test_summarize_card_scope_topic_rebuilds_topics_only_from_all_person_cards() -> None:
    class TopicOnlyRepo:
        def __init__(self) -> None:
            self.list_all_person_slugs_called = False
            self.fetch_person_slugs_seen: list[str] | None = None
            self.topic_cards: list[dict] = []
            self.replace_existing_flags: list[bool] = []

        def list_all_person_slugs(self) -> list[str]:
            self.list_all_person_slugs_called = True
            return ["people/a", "people/b"]

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            _ = paper_slugs
            raise AssertionError("topic scope must not load people from linked paper subsets")

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            self.fetch_person_slugs_seen = list(person_slugs)
            return [
                {"slug": "people/a", "type": "person", "related_papers": ["papers/article-a"]},
                {"slug": "people/b", "type": "person", "related_papers": ["papers/article-a"]},
            ]

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            self.topic_cards = copy.deepcopy(cards)
            self.replace_existing_flags.append(replace_existing)

        def upsert_paper_card(self, card: dict) -> None:
            _ = card
            raise AssertionError("paper cards must not be upserted for topic scope")

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("person cards must not be upserted for topic scope")

    class TopicOnlyLLM:
        def __init__(self) -> None:
            self.topic_input: list[dict] | None = None

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text, metadata
            raise AssertionError("paper summarization must not run for topic scope")

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            raise AssertionError("person derivation must not run for topic scope")

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            self.topic_input = list(person_cards)
            return [
                {
                    "slug": "topics/t1",
                    "type": "topic",
                    "topic": "Topic 1",
                    "related_people": ["people/a", "people/b"],
                }
            ]

    repo = TopicOnlyRepo()
    llm = TopicOnlyLLM()
    result = SummarizeService(repo=repo, llm=llm).run(card_scope="topic")

    assert repo.list_all_person_slugs_called is True
    assert repo.fetch_person_slugs_seen == ["people/a", "people/b"]
    assert [card["slug"] for card in llm.topic_input or []] == ["people/a", "people/b"]
    assert repo.replace_existing_flags == [True]
    assert [card["slug"] for card in repo.topic_cards] == ["topics/t1"]
    assert result.paper_cards == 0
    assert result.person_cards == 0
    assert result.topic_cards == 1


def test_summarize_card_scope_topic_skips_upsert_when_no_source_person_cards() -> None:
    class TopicScopeEmptySourceRepo:
        def __init__(self) -> None:
            self.upsert_calls = 0

        def list_all_person_slugs(self) -> list[str]:
            return []

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            assert person_slugs == []
            return []

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            self.upsert_calls += 1

    class TopicScopeEmptySourceLLM:
        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            assert person_cards == []
            return []

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text, metadata
            raise AssertionError("paper summarization must not run for topic scope")

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            raise AssertionError("person derivation must not run for topic scope")

    repo = TopicScopeEmptySourceRepo()
    result = SummarizeService(repo=repo, llm=TopicScopeEmptySourceLLM()).run(card_scope="topic")

    assert repo.upsert_calls == 0
    assert result.paper_cards == 0
    assert result.person_cards == 0
    assert result.topic_cards == 0


def test_summarize_rejects_invalid_card_scope() -> None:
    repo = FakeRepo()
    llm = FakeLLM()

    with pytest.raises(ValueError, match=r"Invalid card_scope"):
        SummarizeService(repo=repo, llm=llm).run(card_scope="invalid")


def test_summarize_incremental_related_only_updates_affected_people_and_topics() -> None:
    class IncrementalRepo:
        def __init__(self) -> None:
            self.force_all_seen: bool | None = None
            self.paper_cards: list[dict] = []
            self.person_cards: list[dict] = []
            self.topic_cards: list[dict] = []
            self.person_replace_existing_flags: list[bool] = []
            self.topic_replace_existing_flags: list[bool] = []
            self.person_slugs_from_new_papers_seen: list[str] | None = None
            self.paper_slugs_for_people_seen: list[str] | None = None
            self.topic_slugs_for_people_seen: list[str] | None = None
            self.person_slugs_for_topics_seen: list[str] | None = None
            self.fetch_paper_slugs_seen: list[str] | None = None
            self.fetch_person_slugs_seen: list[str] | None = None

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            self.force_all_seen = force_all
            return [
                FakePaper(
                    slug="papers/new-article",
                    title="New Article",
                    journal="J",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["A <a@example.org>"],
                    full_text="A",
                ),
                FakePaper(
                    slug="papers/new-review",
                    title="New Review",
                    journal="J",
                    year=2024,
                    authors=["B"],
                    corresponding_authors=["B <b@example.org>"],
                    full_text="B",
                ),
            ]

        def upsert_paper_card(self, card: dict) -> None:
            self.paper_cards.append(copy.deepcopy(card))

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            self.person_slugs_from_new_papers_seen = list(paper_slugs)
            return ["people/existing"]

        def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            self.paper_slugs_for_people_seen = sorted(person_slugs)
            # Simulate stale link tables before new links are written.
            return ["papers/context-article"]

        def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
            self.fetch_paper_slugs_seen = sorted(paper_slugs)
            by_slug = {
                "papers/context-article": {"slug": "papers/context-article", "type": "article", "paper_type": "article"},
                "papers/new-article": {"slug": "papers/new-article", "type": "article", "paper_type": "article"},
                "papers/new-review": {"slug": "papers/new-review", "type": "article", "paper_type": "review"},
            }
            return [copy.deepcopy(by_slug[slug]) for slug in paper_slugs if slug in by_slug]

        def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            self.topic_slugs_for_people_seen = sorted(person_slugs)
            return ["topics/existing-topic"]

        def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
            self.person_slugs_for_topics_seen = list(topic_slugs)
            return ["people/context-only", "people/existing", "people/new-author"]

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            self.fetch_person_slugs_seen = sorted(person_slugs)
            return [
                {"slug": "people/context-only", "type": "person", "related_papers": ["papers/context-article"]},
                {"slug": "people/existing", "type": "person", "related_papers": ["papers/context-article"]},
                {"slug": "people/new-author", "type": "person", "related_papers": ["papers/new-article"]},
            ]

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            self.person_cards = copy.deepcopy(cards)
            self.person_replace_existing_flags.append(replace_existing)

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            self.topic_cards = copy.deepcopy(cards)
            self.topic_replace_existing_flags.append(replace_existing)

    class IncrementalLLM:
        def __init__(self) -> None:
            self.person_inputs: list[list[str]] = []
            self.topic_inputs: list[list[str]] = []

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            paper_type = "article" if metadata["slug"] == "papers/new-article" else "review"
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": paper_type,
                "title": metadata["title"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            slugs = [card["slug"] for card in paper_cards]
            self.person_inputs.append(slugs)
            if slugs == ["papers/new-article"]:
                return [
                    {
                        "slug": "people/new-author",
                        "type": "person",
                        "related_papers": ["papers/new-article"],
                    }
                ]

            cards = [
                {
                    "slug": "people/context-only",
                    "type": "person",
                    "related_papers": ["papers/context-article"],
                },
                {
                    "slug": "people/existing",
                    "type": "person",
                    "related_papers": ["papers/context-article"],
                },
            ]
            if "papers/new-article" in slugs:
                cards.append(
                    {
                        "slug": "people/new-author",
                        "type": "person",
                        "related_papers": ["papers/new-article"],
                    }
                )
            return cards

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            slugs = [card["slug"] for card in person_cards]
            self.topic_inputs.append(slugs)
            return [
                {
                    "slug": "topics/context-topic",
                    "type": "topic",
                    "topic": "Context Topic",
                    "related_people": ["people/context-only"],
                },
                {
                    "slug": "topics/existing-topic",
                    "type": "topic",
                    "topic": "Existing Topic",
                    "related_people": ["people/existing", "people/new-author"],
                },
                {
                    "slug": "topics/new-related-topic",
                    "type": "topic",
                    "topic": "New Related Topic",
                    "related_people": ["people/new-author"],
                },
            ]

    repo = IncrementalRepo()
    llm = IncrementalLLM()
    result = SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert repo.force_all_seen is False
    assert [card["slug"] for card in repo.paper_cards] == ["papers/new-article", "papers/new-review"]
    assert repo.person_slugs_from_new_papers_seen == ["papers/new-article", "papers/new-review"]
    assert repo.paper_slugs_for_people_seen == ["people/existing", "people/new-author"]
    assert repo.fetch_paper_slugs_seen == ["papers/context-article", "papers/new-article", "papers/new-review"]
    assert repo.topic_slugs_for_people_seen == ["people/existing", "people/new-author"]
    assert repo.person_slugs_for_topics_seen == ["topics/existing-topic"]
    assert repo.fetch_person_slugs_seen == ["people/context-only", "people/existing", "people/new-author"]
    assert llm.person_inputs == [
        ["papers/new-article"],
        ["papers/context-article", "papers/new-article"],
    ]
    assert llm.topic_inputs == [["people/context-only", "people/existing", "people/new-author"]]
    assert repo.person_replace_existing_flags == [False]
    assert repo.topic_replace_existing_flags == [False]
    assert [card["slug"] for card in repo.person_cards] == ["people/existing", "people/new-author"]
    assert [card["slug"] for card in repo.topic_cards] == [
        "topics/existing-topic",
        "topics/new-related-topic",
    ]
    assert repo.person_cards[0]["focus_area"] == ["Existing Topic"]
    assert repo.person_cards[1]["focus_area"] == ["Existing Topic", "New Related Topic"]
    assert result.paper_cards == 2
    assert result.person_cards == 2
    assert result.topic_cards == 2


def test_summarize_incremental_topics_use_regenerated_person_cards_for_affected_people() -> None:
    class IncrementalMergeRepo:
        def __init__(self) -> None:
            self.paper_cards: list[dict] = []
            self.person_cards: list[dict] = []
            self.topic_cards: list[dict] = []

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            return [
                FakePaper(
                    slug="papers/new-article",
                    title="New Article",
                    journal="J",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["A <a@example.org>"],
                    full_text="A",
                ),
                FakePaper(
                    slug="papers/new-review",
                    title="New Review",
                    journal="J",
                    year=2024,
                    authors=["B"],
                    corresponding_authors=["B <b@example.org>"],
                    full_text="B",
                ),
            ]

        def upsert_paper_card(self, card: dict) -> None:
            self.paper_cards.append(copy.deepcopy(card))

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            _ = paper_slugs
            return ["people/existing"]

        def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            return ["papers/context-article"]

        def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
            by_slug = {
                "papers/context-article": {"slug": "papers/context-article", "type": "article", "paper_type": "article"},
                "papers/new-article": {"slug": "papers/new-article", "type": "article", "paper_type": "article"},
                "papers/new-review": {"slug": "papers/new-review", "type": "article", "paper_type": "review"},
            }
            return [copy.deepcopy(by_slug[slug]) for slug in paper_slugs if slug in by_slug]

        def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            return ["topics/existing-topic"]

        def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
            _ = topic_slugs
            return ["people/context-only", "people/existing"]

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            _ = person_slugs
            return [
                {"slug": "people/context-only", "type": "person", "state": "db"},
                {"slug": "people/existing", "type": "person", "state": "stale"},
            ]

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.person_cards = copy.deepcopy(cards)

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.topic_cards = copy.deepcopy(cards)

    class IncrementalMergeLLM:
        def __init__(self) -> None:
            self.topic_input_state: dict[str, str] = {}

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            paper_type = "article" if metadata["slug"] == "papers/new-article" else "review"
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": paper_type,
                "title": metadata["title"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            slugs = [card["slug"] for card in paper_cards]
            if slugs == ["papers/new-article"]:
                return [{"slug": "people/new-author", "type": "person"}]
            return [
                {
                    "slug": "people/existing",
                    "type": "person",
                    "state": "regenerated",
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            self.topic_input_state = {
                str(card.get("slug", "")).strip(): str(card.get("state", "")).strip() for card in person_cards
            }
            return [
                {
                    "slug": "topics/existing-topic",
                    "type": "topic",
                    "topic": "Existing Topic",
                    "related_people": ["people/existing"],
                }
            ]

    repo = IncrementalMergeRepo()
    llm = IncrementalMergeLLM()

    SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert llm.topic_input_state == {
        "people/context-only": "db",
        "people/existing": "regenerated",
    }
    assert repo.person_cards[0]["focus_area"] == ["Existing Topic"]
    assert [card["slug"] for card in repo.topic_cards] == ["topics/existing-topic"]


def test_summarize_incremental_derives_topics_when_affected_topic_slugs_empty() -> None:
    class IncrementalNoTopicLinksRepo:
        def __init__(self) -> None:
            self.topic_lookup_person_slugs_seen: list[str] | None = None
            self.topic_cards: list[dict] = []

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            return [
                FakePaper(
                    slug="papers/new-article",
                    title="New Article",
                    journal="J",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["A <a@example.org>"],
                    full_text="A",
                )
            ]

        def upsert_paper_card(self, card: dict) -> None:
            _ = card

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            _ = paper_slugs
            return []

        def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            return []

        def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
            return [
                {"slug": slug, "type": "article", "paper_type": "article"}
                for slug in paper_slugs
                if slug == "papers/new-article"
            ]

        def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            self.topic_lookup_person_slugs_seen = list(person_slugs)
            return []

        def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
            _ = topic_slugs
            raise AssertionError("topic-person backfill should not run without affected topic slugs")

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            _ = person_slugs
            raise AssertionError("person fetch by topic links should not run without affected topic slugs")

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.topic_cards = copy.deepcopy(cards)

    class IncrementalNoTopicLinksLLM:
        def __init__(self) -> None:
            self.topic_inputs: list[list[str]] = []

        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "article",
                "title": metadata["title"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            return [
                {
                    "slug": "people/new-author",
                    "type": "person",
                    "related_papers": ["papers/new-article"],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            self.topic_inputs.append([card["slug"] for card in person_cards])
            return [
                {
                    "slug": "topics/new-topic",
                    "type": "topic",
                    "topic": "New Topic",
                    "related_people": ["people/new-author"],
                },
                {
                    "slug": "topics/unrelated-topic",
                    "type": "topic",
                    "topic": "Unrelated Topic",
                    "related_people": ["people/someone-else"],
                },
            ]

    repo = IncrementalNoTopicLinksRepo()
    llm = IncrementalNoTopicLinksLLM()
    result = SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert repo.topic_lookup_person_slugs_seen == ["people/new-author"]
    assert llm.topic_inputs == [["people/new-author"]]
    assert [card["slug"] for card in repo.topic_cards] == ["topics/new-topic"]
    assert result.topic_cards == 1


def test_summarize_incremental_raises_value_error_when_topics_empty_for_affected_people() -> None:
    class IncrementalNoTopicLinksRepo:
        def __init__(self) -> None:
            self.person_cards: list[dict] = []
            self.topic_cards: list[dict] = []

        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            return [
                FakePaper(
                    slug="papers/new-article",
                    title="New Article",
                    journal="J",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["A <a@example.org>"],
                    full_text="A",
                )
            ]

        def upsert_paper_card(self, card: dict) -> None:
            _ = card

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            _ = paper_slugs
            return []

        def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            return []

        def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
            return [
                {"slug": slug, "type": "article", "paper_type": "article"}
                for slug in paper_slugs
                if slug == "papers/new-article"
            ]

        def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            return []

        def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
            _ = topic_slugs
            raise AssertionError("topic-person backfill should not run without affected topic slugs")

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            _ = person_slugs
            raise AssertionError("person fetch by topic links should not run without affected topic slugs")

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.person_cards = copy.deepcopy(cards)

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = replace_existing
            self.topic_cards = copy.deepcopy(cards)

    class IncrementalNoTopicsLLM:
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "article",
                "title": metadata["title"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            return [
                {
                    "slug": "people/new-author",
                    "type": "person",
                    "related_papers": ["papers/new-article"],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            return []

    repo = IncrementalNoTopicLinksRepo()
    llm = IncrementalNoTopicsLLM()

    with pytest.raises(ValueError, match=r"No linked topics found for person card"):
        SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert repo.person_cards == []
    assert repo.topic_cards == []


def test_summarize_incremental_returns_noop_when_no_new_papers() -> None:
    class NoNewPapersRepo:
        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            _ = force_all
            return []

        def upsert_paper_card(self, card: dict) -> None:
            _ = card
            raise AssertionError("paper upsert should not run when no papers are returned")

        def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
            _ = paper_slugs
            raise AssertionError("person lookup should not run when no new paper cards exist")

        def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            raise AssertionError("paper backfill should not run when no new paper cards exist")

        def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
            _ = paper_slugs
            raise AssertionError("paper fetch should not run when no new paper cards exist")

        def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
            _ = person_slugs
            raise AssertionError("topic lookup should not run when no new paper cards exist")

        def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
            _ = topic_slugs
            raise AssertionError("person-topic backfill should not run when no new paper cards exist")

        def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
            _ = person_slugs
            raise AssertionError("person fetch should not run when no new paper cards exist")

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("person upsert should not run when no new paper cards exist")

        def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            _ = cards, replace_existing
            raise AssertionError("topic upsert should not run when no new paper cards exist")

    class NoNewPapersLLM:
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text, metadata
            raise AssertionError("paper summarization should not run when no papers are returned")

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            _ = paper_cards
            raise AssertionError("person derivation should not run when no new paper cards exist")

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            raise AssertionError("topic derivation should not run when no new paper cards exist")

    result = SummarizeService(repo=NoNewPapersRepo(), llm=NoNewPapersLLM()).run(card_scope=None)

    assert result.paper_cards == 0
    assert result.person_cards == 0
    assert result.topic_cards == 0


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
                "paper_type": "article",
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
    result = SummarizeService(repo=repo, llm=llm).run(card_scope="all")

    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1


def test_summarize_focus_area_and_topic_links_from_generated_topics() -> None:
    class TopicLinkRepo(FakeRepo):
        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            self.force_all_seen = force_all
            return [
                FakePaper(
                    slug="papers/topic-link",
                    title="Topic Link Paper",
                    journal="Nature",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=["Alice Research <alice@university.org>"],
                    full_text="topic-link text",
                )
            ]

    class TopicLinkLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "article",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "type": "topic",
                    "topic": "Cancer Genetics",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    repo = TopicLinkRepo()
    llm = TopicLinkLLM()

    result = SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1
    assert repo.person_cards[0]["focus_area"] == ["Cancer Genetics"]
    assert repo.topic_cards[0]["related_people"] == ["people/alice-university-org"]


def test_summarize_raises_value_error_when_person_has_no_linked_topic() -> None:
    class MissingTopicRepo(FakeRepo):
        def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
            self.force_all_seen = force_all
            return [
                FakePaper(
                    slug="papers/missing-topic",
                    title="Missing Topic Paper",
                    journal="Nature",
                    year=2024,
                    authors=["A"],
                    corresponding_authors=[
                        "Alice Research <alice@university.org>",
                        "Bob Research <bob@university.org>",
                    ],
                    full_text="missing-topic text",
                )
            ]

    class MissingTopicLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "article",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                },
                {
                    "slug": "people/bob-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                },
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "type": "topic",
                    "topic": "Cancer Genetics",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    repo = MissingTopicRepo()
    llm = MissingTopicLLM()

    with pytest.raises(ValueError, match=r"No linked topics found for person card"):
        SummarizeService(repo=repo, llm=llm).run(card_scope=None)


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


def test_summarize_does_not_delete_existing_paper_links_when_cards_omit_paper_relations() -> None:
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
                "paper_type": "article",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "focus_area": "Cancer genomics",
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genomics",
                    "type": "topic",
                    "topic": "Cancer Genomics",
                    "related_people": [person_cards[0]["slug"]],
                }
            ]

    result = SummarizeService(repo=repo, llm=SparseLLM()).run(card_scope=None)

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "DELETE FROM paper_person_links" not in executed_sql
    assert "DELETE FROM paper_topic_links" not in executed_sql
    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1


def test_summarize_populates_empty_focus_area_from_generated_topics() -> None:
    class FocusAreaLLM(FakeLLM):
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                    "focus_area": [],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "type": "topic",
                    "topic": "Cancer Genetics",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    repo = FakeRepo()
    llm = FocusAreaLLM()
    SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert repo.person_cards[0]["focus_area"] == ["Cancer Genetics"]


def test_summarize_derives_topics_before_persisting_people() -> None:
    class TwoPassLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__()
            self.topic_derived = False

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            self.topic_derived = True
            return super().derive_topic_cards(person_cards)

    class OrderCheckingRepo(FakeRepo):
        def __init__(self, llm: TwoPassLLM) -> None:
            super().__init__()
            self._llm = llm

        def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
            assert self._llm.topic_derived is True
            super().upsert_person_cards(cards, replace_existing=replace_existing)

    llm = TwoPassLLM()
    repo = OrderCheckingRepo(llm)
    SummarizeService(repo=repo, llm=llm).run(card_scope=None)


def test_summarize_no_linked_topic_raises_value_error() -> None:
    class NoTopicLinkLLM(FakeLLM):
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
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
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "type": "topic",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    repo = FakeRepo()
    with pytest.raises(ValueError, match=r"No linked topics found for person card"):
        SummarizeService(repo=repo, llm=NoTopicLinkLLM()).run(card_scope=None)

    assert repo.calls == ["paper", "paper"]
    assert repo.person_cards == []
    assert repo.topic_cards == []


def test_summarize_article_cards_only_used_for_person_derivation() -> None:
    class MixedCardTypesLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            if metadata["slug"] == "papers/chen-p53-nature-2024-abc123":
                return {
                    "slug": metadata["slug"],
                    "type": "article",
                    "paper_type": "article",
                    "title": metadata["title"],
                    "summary": "article summary",
                    "corresponding_authors": metadata["corresponding_authors"],
                }
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "review",
                "title": metadata["title"],
                "summary": "review summary",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            assert [card["slug"] for card in paper_cards] == ["papers/chen-p53-nature-2024-abc123"]
            assert [card["paper_type"] for card in paper_cards] == ["article"]
            assert [card["type"] for card in paper_cards] == ["article"]
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-genetics",
                    "type": "topic",
                    "topic": "Cancer Genetics",
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    repo = FakeRepo()
    llm = MixedCardTypesLLM()

    result = SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert result.paper_cards == 2
    assert result.person_cards == 1
    assert result.topic_cards == 1


def test_summarize_review_only_papers_produce_no_person_or_topic_cards() -> None:
    class ReviewOnlyLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "review",
                "title": metadata["title"],
                "summary": "review summary",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            self.person_input = list(paper_cards)
            return []

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            self.topic_input = list(person_cards)
            return []

    repo = FakeRepo()
    llm = ReviewOnlyLLM()

    result = SummarizeService(repo=repo, llm=llm).run(card_scope=None)

    assert llm.person_input == []
    assert llm.topic_input is None
    assert repo.person_cards == []
    assert repo.topic_cards == []
    assert result.person_cards == 0
    assert result.topic_cards == 0
