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
    return [
        {
            "slug": "topics/research-synthesis",
            "type": "topic",
            "topic": "Research Synthesis",
        }
    ]


class OpenAISummaryAdapter:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self.client = client
        self.model = model

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        summary = self.client.summarize(paper_text, model=self.model)
        return {
            "slug": metadata["slug"],
            "type": "article",
            "title": metadata.get("title", "Untitled"),
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
