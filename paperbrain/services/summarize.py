from typing import Protocol

from paperbrain.models import SummaryStats


class SummaryRepository(Protocol):
    def list_papers_for_summary(self, force_all: bool) -> list:
        ...

    def upsert_paper_card(self, card: dict) -> None:
        ...

    def upsert_person_cards(self, cards: list[dict]) -> None:
        ...

    def upsert_topic_cards(self, cards: list[dict]) -> None:
        ...


class LLM(Protocol):
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        ...

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        ...

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        ...


class SummarizeService:
    def __init__(self, *, repo: SummaryRepository, llm: LLM) -> None:
        self.repo = repo
        self.llm = llm

    def run(self, force_all: bool) -> SummaryStats:
        papers = self.repo.list_papers_for_summary(force_all)
        paper_cards: list[dict] = []
        for paper in papers:
            metadata = {
                "slug": paper.slug,
                "title": paper.title,
                "journal": paper.journal,
                "year": paper.year,
                "authors": paper.authors,
                "corresponding_authors": paper.corresponding_authors,
            }
            card = self.llm.summarize_paper(paper.full_text, metadata)
            self.repo.upsert_paper_card(card)
            paper_cards.append(card)

        person_cards = self.llm.derive_person_cards(paper_cards)
        self.repo.upsert_person_cards(person_cards)

        topic_cards = self.llm.derive_topic_cards(person_cards)
        self.repo.upsert_topic_cards(topic_cards)

        return SummaryStats(
            paper_cards=len(paper_cards),
            person_cards=len(person_cards),
            topic_cards=len(topic_cards),
        )
