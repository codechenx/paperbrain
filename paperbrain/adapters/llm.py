from typing import Protocol

from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.utils import normalize_email, slugify


class LLMAdapter(Protocol):
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        ...

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        ...

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        ...


def _derive_person_cards(paper_cards: list[dict]) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()
    for paper_card in paper_cards:
        for author in paper_card.get("corresponding_authors", []):
            email = normalize_email(author)
            if not email or email in seen:
                continue
            seen.add(email)
            cards.append(
                {
                    "slug": f"people/{slugify(email)}",
                    "type": "person",
                    "email": email,
                    "focus_area": "Research synthesis",
                }
            )
    return cards


def _derive_topic_cards(person_cards: list[dict]) -> list[dict]:
    if not person_cards:
        return []

    def _as_list(value: object) -> list[str]:
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, list):
            output: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized = item.strip()
                else:
                    normalized = str(item).strip()
                if normalized:
                    output.append(normalized)
            return output
        return []

    def _collect_themes(person_card: dict) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for candidate in (
            _as_list(person_card.get("focus_area"))
            + _as_list(person_card.get("question_themes"))
            + _as_list(person_card.get("big_questions"))
        ):
            normalized = " ".join(candidate.split())
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output

    def _collect_related_papers(person_card: dict) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for key in ("related_papers", "paper_slugs", "papers"):
            for slug in _as_list(person_card.get(key)):
                if slug in seen:
                    continue
                seen.add(slug)
                output.append(slug)
        return output

    topic_cards_by_slug: dict[str, dict] = {}
    for person_card in person_cards:
        person_slug = str(person_card.get("slug", "")).strip()
        related_papers = _collect_related_papers(person_card)
        for theme in _collect_themes(person_card):
            theme_slug = slugify(theme)
            if not theme_slug:
                continue
            topic_slug = f"topics/{theme_slug}"
            topic_card = topic_cards_by_slug.setdefault(
                topic_slug,
                {
                    "slug": topic_slug,
                    "type": "topic",
                    "topic": theme,
                    "related_people": [],
                    "related_papers": [],
                },
            )
            if person_slug and person_slug not in topic_card["related_people"]:
                topic_card["related_people"].append(person_slug)
            for paper_slug in related_papers:
                if paper_slug not in topic_card["related_papers"]:
                    topic_card["related_papers"].append(paper_slug)

    return [topic_cards_by_slug[slug] for slug in sorted(topic_cards_by_slug)]


class OpenAISummaryAdapter:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self.client = client
        self.model = model

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        title = metadata.get("title", "Untitled")
        prompt = f"{title}\n\n{paper_text[:8000]}"
        summary = self.client.summarize(prompt, model=self.model)
        return {
            "slug": metadata["slug"],
            "type": "article",
            "title": title,
            "summary": summary,
            "corresponding_authors": metadata.get("corresponding_authors", []),
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        return _derive_person_cards(paper_cards)

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        return _derive_topic_cards(person_cards)


class DeterministicLLMAdapter:
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        title = metadata.get("title", "Untitled")
        prompt_excerpt = paper_text[:200].strip()
        summary = (
            f"Key question solved: {title}\n"
            f"Why this question is important: Supports corpus-level discovery.\n"
            f"How the paper solves this question: Deterministic scaffold summary.\n"
            f"Key findings and flow: {prompt_excerpt or 'No text content available.'}\n"
            f"Limitations of the paper: Needs full LLM integration for richer synthesis."
        )
        return {
            "slug": metadata["slug"],
            "type": "article",
            "title": title,
            "summary": summary,
            "corresponding_authors": metadata.get("corresponding_authors", []),
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        return _derive_person_cards(paper_cards)

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        return _derive_topic_cards(person_cards)
