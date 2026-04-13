import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from paperbrain.db import connect
from paperbrain.exporter import (
    render_paper_markdown,
    render_person_markdown,
    render_topic_markdown,
    write_markdown,
)


@dataclass(slots=True)
class ExportStats:
    papers: int
    people: int
    topics: int
    files_written: int


class ExportRepository(Protocol):
    def list_paper_cards(self) -> list[dict]:
        ...

    def list_person_cards(self) -> list[dict]:
        ...

    def list_topic_cards(self) -> list[dict]:
        ...


class DatabaseExportRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @staticmethod
    def _decode_card(slug: str, body: Any) -> dict:
        if isinstance(body, dict):
            card = dict(body)
        elif isinstance(body, str):
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"body": body}
            card = dict(parsed) if isinstance(parsed, dict) else {"body": body}
        else:
            card = {"body": str(body)}
        card.setdefault("slug", slug)
        return card

    def _fetch_cards(self, table: str) -> list[dict]:
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT slug, body FROM {table} ORDER BY slug;")
            rows = cursor.fetchall()
        return [self._decode_card(str(slug), body) for slug, body in rows]

    def list_paper_cards(self) -> list[dict]:
        return self._fetch_cards("paper_cards")

    def list_person_cards(self) -> list[dict]:
        return self._fetch_cards("person_cards")

    def list_topic_cards(self) -> list[dict]:
        return self._fetch_cards("topic_cards")


def _as_slug_list(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, tuple):
        values = list(value)
    elif isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    else:
        return []

    output: list[str] = []
    seen: set[str] = set()
    for candidate in values:
        slug = str(candidate).strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        output.append(slug)
    return output


def export_markdown_files(output_dir: Path, pages: dict[str, str]) -> int:
    count = 0
    for relative_path, content in pages.items():
        write_markdown(output_dir / relative_path, content)
        count += 1
    return count


class ExportService:
    def __init__(self, *, repo: ExportRepository) -> None:
        self.repo = repo

    def export(self, output_dir: Path) -> ExportStats:
        paper_cards = self.repo.list_paper_cards()
        person_cards = self.repo.list_person_cards()
        topic_cards = self.repo.list_topic_cards()

        paper_slugs = {str(card.get("slug", "")).strip() for card in paper_cards}
        topic_links_by_person: dict[str, set[str]] = {}
        for topic in topic_cards:
            topic_slug = str(topic.get("slug", "")).strip()
            for person_slug in _as_slug_list(topic.get("related_people")):
                if topic_slug:
                    topic_links_by_person.setdefault(person_slug, set()).add(topic_slug)

        pages: dict[str, str] = {}
        for card in paper_cards:
            slug = str(card.get("slug", "")).strip()
            if not slug:
                continue
            pages[f"{slug}.md"] = render_paper_markdown(
                slug=slug,
                title=str(card.get("title", "Untitled")),
                authors=_as_slug_list(card.get("authors")),
                corresponding_authors=_as_slug_list(card.get("corresponding_authors")),
                journal=str(card.get("journal", "Unknown")),
                year=int(card.get("year", 0) or 0),
                summary_block=str(card.get("summary", card.get("body", ""))),
                related_topics=_as_slug_list(card.get("related_topics")),
            )

        for card in person_cards:
            slug = str(card.get("slug", "")).strip()
            if not slug:
                continue
            related_papers = [paper for paper in _as_slug_list(card.get("related_papers")) if paper in paper_slugs]
            related_topics = sorted(topic_links_by_person.get(slug, set()))
            pages[f"{slug}.md"] = render_person_markdown(
                slug=slug,
                name=str(card.get("name", slug.split("/")[-1])),
                related_papers=related_papers,
                related_topics=related_topics,
            )

        for card in topic_cards:
            slug = str(card.get("slug", "")).strip()
            if not slug:
                continue
            pages[f"{slug}.md"] = render_topic_markdown(
                slug=slug,
                topic=str(card.get("topic", slug.split("/")[-1])),
                related_papers=_as_slug_list(card.get("related_papers")),
                related_people=_as_slug_list(card.get("related_people")),
            )

        files_written = export_markdown_files(output_dir, pages)
        return ExportStats(
            papers=len([card for card in paper_cards if str(card.get("slug", "")).strip()]),
            people=len([card for card in person_cards if str(card.get("slug", "")).strip()]),
            topics=len([card for card in topic_cards if str(card.get("slug", "")).strip()]),
            files_written=files_written,
        )


def run_export(database_url: str, output_dir: Path) -> ExportStats:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")

    with connect(database_url, autocommit=False) as connection:
        service = ExportService(repo=DatabaseExportRepository(connection))
        return service.export(output_dir)
