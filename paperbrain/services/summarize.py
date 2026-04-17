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

    def list_all_person_slugs(self) -> list[str]:
        ...

    def list_person_slugs_linked_to_paper_slugs(self, paper_slugs: list[str]) -> list[str]:
        ...

    def list_topic_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        ...

    def list_paper_slugs_linked_to_person_slugs(self, person_slugs: list[str]) -> list[str]:
        ...

    def list_person_slugs_linked_to_topic_slugs(self, topic_slugs: list[str]) -> list[str]:
        ...

    def fetch_paper_cards_by_slugs(self, paper_slugs: list[str]) -> list[dict]:
        ...

    def fetch_all_paper_cards(self) -> list[dict]:
        ...

    def fetch_person_cards_by_slugs(self, person_slugs: list[str]) -> list[dict]:
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
        if normalized_scope == "paper":
            paper_cards = self._summarize_and_upsert_papers(force_all=True)
            return SummaryStats(paper_cards=len(paper_cards), person_cards=0, topic_cards=0)

        if normalized_scope == "person":
            paper_cards = self._fetch_all_paper_cards()
            source_article_cards = self._article_cards(paper_cards)
            if not source_article_cards:
                return SummaryStats(paper_cards=0, person_cards=0, topic_cards=0)
            person_cards = self.llm.derive_person_cards(source_article_cards)
            self.repo.upsert_person_cards(person_cards, replace_existing=True)
            return SummaryStats(paper_cards=0, person_cards=len(person_cards), topic_cards=0)

        if normalized_scope == "topic":
            person_cards = self._fetch_all_person_cards()
            if not person_cards:
                return SummaryStats(paper_cards=0, person_cards=0, topic_cards=0)
            topic_cards = self.llm.derive_topic_cards(person_cards)
            self.repo.upsert_topic_cards(topic_cards, replace_existing=True)
            return SummaryStats(paper_cards=0, person_cards=0, topic_cards=len(topic_cards))

        if normalized_scope == "all":
            paper_cards = self._summarize_and_upsert_papers(force_all=True)
            person_cards = self.llm.derive_person_cards(self._article_cards(paper_cards))
            topic_cards = self.llm.derive_topic_cards(person_cards)
            if person_cards:
                _apply_person_focus_areas(person_cards, topic_cards)
            self.repo.upsert_person_cards(person_cards, replace_existing=True)
            self.repo.upsert_topic_cards(topic_cards, replace_existing=True)
            return SummaryStats(
                paper_cards=len(paper_cards),
                person_cards=len(person_cards),
                topic_cards=len(topic_cards),
            )

        paper_cards = self._summarize_and_upsert_papers(force_all=False)
        if not paper_cards:
            return SummaryStats(paper_cards=0, person_cards=0, topic_cards=0)
        new_paper_slugs = self._card_slugs(paper_cards)
        derived_from_new_articles = self.llm.derive_person_cards(self._article_cards(paper_cards))
        derived_person_slugs = self._card_slugs(derived_from_new_articles)
        affected_person_slugs = self._merge_unique_slugs(
            self.repo.list_person_slugs_linked_to_paper_slugs(new_paper_slugs),
            derived_person_slugs,
        )

        regenerated_person_cards: list[dict] = []
        if affected_person_slugs:
            linked_context_paper_slugs = self.repo.list_paper_slugs_linked_to_person_slugs(affected_person_slugs)
            context_paper_slugs = self._merge_unique_slugs(linked_context_paper_slugs, new_paper_slugs)
            context_paper_cards = self.repo.fetch_paper_cards_by_slugs(context_paper_slugs)
            regenerated_person_cards = self.llm.derive_person_cards(self._article_cards(context_paper_cards))
        affected_person_slug_set = set(affected_person_slugs)
        affected_person_cards = [
            card
            for card in regenerated_person_cards
            if str(card.get("slug", "")).strip() in affected_person_slug_set
        ]

        affected_topic_slugs = self.repo.list_topic_slugs_linked_to_person_slugs(affected_person_slugs)
        regenerated_topic_cards: list[dict] = []
        affected_person_cards_by_slug = {
            slug: card
            for card in affected_person_cards
            if (slug := str(card.get("slug", "")).strip())
        }
        topic_input_person_cards: list[dict] = []
        if affected_topic_slugs:
            context_person_slugs = self.repo.list_person_slugs_linked_to_topic_slugs(affected_topic_slugs)
            context_person_cards = self.repo.fetch_person_cards_by_slugs(context_person_slugs)
            seen_person_slugs: set[str] = set()
            for card in context_person_cards:
                slug = str(card.get("slug", "")).strip()
                if not slug:
                    continue
                seen_person_slugs.add(slug)
                topic_input_person_cards.append(affected_person_cards_by_slug.get(slug, card))
            for slug, card in affected_person_cards_by_slug.items():
                if slug not in seen_person_slugs:
                    topic_input_person_cards.append(card)
        elif affected_person_cards_by_slug:
            topic_input_person_cards = list(affected_person_cards_by_slug.values())
        if topic_input_person_cards:
            regenerated_topic_cards = self.llm.derive_topic_cards(topic_input_person_cards)
        affected_topic_slug_set = set(affected_topic_slugs)
        topic_cards = [
            card
            for card in regenerated_topic_cards
            if (
                str(card.get("slug", "")).strip() in affected_topic_slug_set
                or bool(set(_as_string_list(card.get("related_people"))) & affected_person_slug_set)
            )
        ]

        if affected_person_cards:
            _apply_person_focus_areas(affected_person_cards, topic_cards)

        self.repo.upsert_person_cards(affected_person_cards, replace_existing=False)
        self.repo.upsert_topic_cards(topic_cards, replace_existing=False)
        return SummaryStats(
            paper_cards=len(paper_cards),
            person_cards=len(affected_person_cards),
            topic_cards=len(topic_cards),
        )

    def _summarize_and_upsert_papers(self, *, force_all: bool) -> list[dict]:
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
        return paper_cards

    def _fetch_all_paper_cards(self) -> list[dict]:
        return self.repo.fetch_all_paper_cards()

    def _fetch_all_person_cards(self) -> list[dict]:
        person_slugs = self.repo.list_all_person_slugs()
        return self.repo.fetch_person_cards_by_slugs(person_slugs)

    @staticmethod
    def _article_cards(cards: list[dict]) -> list[dict]:
        return [
            card
            for card in cards
            if str(card.get("paper_type", "")).strip().lower() == "article"
        ]

    @staticmethod
    def _card_slugs(cards: list[dict]) -> list[str]:
        slugs: list[str] = []
        seen: set[str] = set()
        for card in cards:
            slug = str(card.get("slug", "")).strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            slugs.append(slug)
        return slugs

    @staticmethod
    def _merge_unique_slugs(*collections: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for values in collections:
            for value in values:
                normalized = str(value).strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                output.append(normalized)
        return output
