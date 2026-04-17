from typing import Protocol

from paperbrain.models import SummaryStats

_SUPPORTED_CARD_SCOPES = {"all", "paper", "person", "topic"}


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized:
                output.append(normalized)
        return output
    return []


def _topic_name(topic_card: dict) -> str:
    for key in ("topic", "name", "title"):
        value = str(topic_card.get(key, "")).strip()
        if value:
            return value
    slug = str(topic_card.get("slug", "")).strip()
    if slug.startswith("topics/"):
        slug = slug.split("/", 1)[1]
    return slug.replace("-", " ").strip()


def _apply_person_focus_areas(person_cards: list[dict], topic_cards: list[dict]) -> None:
    focus_areas_by_person: dict[str, list[str]] = {}
    for topic_card in topic_cards:
        topic_name = _topic_name(topic_card)
        if not topic_name:
            continue
        for person_slug in _as_string_list(topic_card.get("related_people")):
            focus_areas = focus_areas_by_person.setdefault(person_slug, [])
            if topic_name not in focus_areas:
                focus_areas.append(topic_name)

    for person_card in person_cards:
        person_slug = str(person_card.get("slug", "")).strip()
        focus_areas = focus_areas_by_person.get(person_slug, [])
        if not focus_areas:
            raise ValueError(f"No linked topics found for person card: {person_slug or '(missing slug)'}")
        person_card["focus_area"] = focus_areas


class SummaryRepository(Protocol):
    def list_papers_for_summary(self, force_all: bool) -> list:
        ...

    def upsert_paper_card(self, card: dict) -> None:
        ...

    def upsert_person_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
        ...

    def upsert_topic_cards(self, cards: list[dict], *, replace_existing: bool = False) -> None:
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

    def run(self, card_scope: str | None = None) -> SummaryStats:
        normalized_scope = card_scope.strip().lower() if card_scope is not None else None
        if normalized_scope is not None and normalized_scope not in _SUPPORTED_CARD_SCOPES:
            allowed = ", ".join(sorted(_SUPPORTED_CARD_SCOPES))
            raise ValueError(f"Invalid card_scope '{card_scope}'. Allowed values: {allowed}")
        force_all = normalized_scope == "all"
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

        article_paper_cards = [
            card
            for card in paper_cards
            if str(card.get("paper_type", "")).strip().lower() == "article"
        ]
        person_cards = self.llm.derive_person_cards(article_paper_cards)
        topic_cards = self.llm.derive_topic_cards(person_cards)

        _apply_person_focus_areas(person_cards, topic_cards)

        self.repo.upsert_person_cards(person_cards, replace_existing=force_all)
        self.repo.upsert_topic_cards(topic_cards, replace_existing=force_all)

        return SummaryStats(
            paper_cards=len(paper_cards),
            person_cards=len(person_cards),
            topic_cards=len(topic_cards),
        )
