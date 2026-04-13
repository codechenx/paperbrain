import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from paperbrain.db import connect
from paperbrain.exporter import (
    render_index_markdown,
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


def _ensure_prefixed_slug(slug: str, prefix: str) -> str:
    normalized = slug.strip().strip("/")
    if not normalized:
        return ""
    if normalized.startswith(f"{prefix}/"):
        return normalized
    return f"{prefix}/{normalized}"


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


def _as_big_question_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            output.append(dict(item))
    return output


def _merge_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _normalize_related_big_questions(value: Any) -> list[dict[str, Any]]:
    entries = _as_big_question_list(value)
    merged_by_question: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in entries:
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        key = question.casefold()
        why = str(item.get("why_important", item.get("why", "(missing)"))).strip() or "(missing)"
        papers = _as_slug_list(item.get("related_papers"))
        people = _as_slug_list(item.get("related_people"))
        if key not in merged_by_question:
            merged_by_question[key] = {
                "question": question,
                "why_important": why,
                "related_papers": papers,
                "related_people": people,
            }
            order.append(key)
            continue
        existing = merged_by_question[key]
        existing["related_papers"] = _merge_unique_strings(_as_slug_list(existing.get("related_papers")) + papers)
        existing["related_people"] = _merge_unique_strings(_as_slug_list(existing.get("related_people")) + people)
        existing_why = str(existing.get("why_important", "")).strip()
        if not existing_why or existing_why == "(missing)":
            existing["why_important"] = why
    return [merged_by_question[key] for key in order]


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
        paper_export_slugs: list[str] = []
        person_export_slugs: list[str] = []
        topic_export_slugs: list[str] = []
        paper_slug_map: dict[str, str] = {}
        person_big_questions: dict[str, list[dict[str, Any]]] = {}
        for card in paper_cards:
            raw_slug = str(card.get("slug", "")).strip()
            if not raw_slug:
                continue
            export_slug = _ensure_prefixed_slug(raw_slug, "papers")
            paper_slug_map[raw_slug] = export_slug
            paper_export_slugs.append(export_slug)
            pages[f"{export_slug}.md"] = render_paper_markdown(
                slug=export_slug,
                paper_type=str(card.get("paper_type", card.get("type", "article"))),
                title=str(card.get("title", "Untitled")),
                authors=_as_slug_list(card.get("authors")),
                corresponding_authors=[
                    _ensure_prefixed_slug(value, "people")
                    if "@" not in value and "/" not in value
                    else value
                    for value in _as_slug_list(card.get("corresponding_authors"))
                ],
                journal=str(card.get("journal", "Unknown")),
                year=int(card.get("year", 0) or 0),
                summary_block=str(card.get("summary", card.get("body", ""))),
                related_topics=[_ensure_prefixed_slug(value, "topics") for value in _as_slug_list(card.get("related_topics"))],
            )

        for card in person_cards:
            slug = str(card.get("slug", "")).strip()
            if not slug:
                continue
            export_slug = _ensure_prefixed_slug(slug, "people")
            person_export_slugs.append(export_slug)
            related_papers = [
                paper_slug_map.get(paper, _ensure_prefixed_slug(paper, "papers"))
                for paper in _as_slug_list(card.get("related_papers"))
                if paper in paper_slugs or _ensure_prefixed_slug(paper, "papers") in paper_export_slugs
            ]
            related_topics = sorted(topic_links_by_person.get(slug, set()))
            focus_areas = _as_slug_list(card.get("focus_area")) + _as_slug_list(card.get("focus_areas"))
            pages[f"{export_slug}.md"] = render_person_markdown(
                slug=export_slug,
                name=str(card.get("name", slug.split("/")[-1])),
                email=str(card.get("email", "")),
                affiliation=str(card.get("affiliation", "Unknown affiliation")),
                focus_areas=focus_areas,
                big_questions=card.get("big_questions", []),
                related_papers=related_papers,
                related_topics=[_ensure_prefixed_slug(topic_slug, "topics") for topic_slug in related_topics],
            )
            normalized_questions = _as_big_question_list(card.get("big_questions"))
            person_big_questions[slug] = normalized_questions
            person_big_questions[export_slug] = normalized_questions

        for card in topic_cards:
            slug = str(card.get("slug", "")).strip()
            if not slug:
                continue
            export_slug = _ensure_prefixed_slug(slug, "topics")
            topic_export_slugs.append(export_slug)
            topic_related_people_raw = _as_slug_list(card.get("related_people"))
            topic_related_people = [_ensure_prefixed_slug(person_slug, "people") for person_slug in topic_related_people_raw]
            related_big_questions = _normalize_related_big_questions(card.get("related_big_questions"))
            if not related_big_questions:
                for person_slug in topic_related_people_raw + topic_related_people:
                    for question in person_big_questions.get(person_slug, []):
                        question_text = str(question.get("question", "")).strip()
                        if not question_text:
                            continue
                        why_text = str(question.get("why_important", question.get("why", "(missing)"))).strip() or "(missing)"
                        related_papers = [
                            paper_slug_map.get(paper, _ensure_prefixed_slug(paper, "papers"))
                            for paper in _as_slug_list(question.get("related_papers"))
                        ]
                        person_export_slug = _ensure_prefixed_slug(person_slug, "people")
                        related_big_questions.append(
                            {
                                "question": question_text,
                                "why_important": why_text,
                                "related_papers": related_papers,
                                "related_people": [person_export_slug],
                            }
                        )
                related_big_questions = _normalize_related_big_questions(related_big_questions)
            pages[f"{export_slug}.md"] = render_topic_markdown(
                slug=export_slug,
                topic=str(card.get("topic", slug.split("/")[-1])),
                related_big_questions=related_big_questions,
                related_papers=[
                    paper_slug_map.get(paper, _ensure_prefixed_slug(paper, "papers"))
                    for paper in _as_slug_list(card.get("related_papers"))
                ],
                related_people=topic_related_people,
            )

        pages["index.md"] = render_index_markdown(
            paper_slugs=paper_export_slugs,
            person_slugs=person_export_slugs,
            topic_slugs=topic_export_slugs,
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
