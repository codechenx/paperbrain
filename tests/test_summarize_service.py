from dataclasses import dataclass

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
    def list_papers_for_summary(self, force_all: bool) -> list[FakePaper]:
        _ = force_all
        return [
            FakePaper(
                slug="papers/chen-p53-nature-2024-abc123",
                title="P53 Mutations and Cancer Progression",
                journal="Nature",
                year=2024,
                authors=["Stephen Chen"],
                corresponding_authors=["Alice Research <alice@university.org>"],
                full_text="P53 mutation study",
            )
        ]

    def upsert_paper_card(self, card: dict) -> None:
        self.paper_card = card

    def upsert_person_cards(self, cards: list[dict]) -> None:
        self.person_cards = cards

    def upsert_topic_cards(self, cards: list[dict]) -> None:
        self.topic_cards = cards


class FakeLLM:
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        _ = paper_text
        return {"slug": metadata["slug"], "type": "article", "summary": "x"}

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        _ = paper_cards
        return [{"slug": "people/alice-university-org", "type": "person"}]

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        _ = person_cards
        return [{"slug": "topics/cancer-genetics", "type": "topic"}]


def test_summarize_creates_paper_person_topic_cards() -> None:
    repo = FakeRepo()
    service = SummarizeService(repo=repo, llm=FakeLLM())
    result = service.run(force_all=True)
    assert result.paper_cards == 1
    assert result.person_cards == 1
    assert result.topic_cards == 1

