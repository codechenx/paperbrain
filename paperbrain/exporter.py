import json
import re
from pathlib import Path


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _wikilinks(values: list[str]) -> str:
    slugs = _dedupe(values)
    if not slugs:
        return "None"
    return ", ".join(f"[[{slug}]]" for slug in slugs)


def _yaml_quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return _dedupe([str(item) for item in value])
    if isinstance(value, str):
        return _dedupe([value])
    return []


def _extract_summary_sections(summary_block: str) -> dict[str, str]:
    keys = [
        "Key question solved",
        "Why this question is important",
        "How the paper solves this question",
        "Key findings and flow",
        "Limitations of the paper",
        "Key goal of the review",
        "Key unsolved questions",
        "Why these unsolved questions are important",
        "Why these unsolved questions are still unsolved",
    ]
    sections = {key: "" for key in keys}

    key_lookup = {key.casefold(): key for key in keys}
    key_pattern = re.compile(
        r"^\s*(Key question solved|Why this question is important|How the paper solves this question|Key findings and flow|Limitations of the paper|Key goal of the review|Key unsolved questions|Why these unsolved questions are important|Why these unsolved questions are still unsolved)\s*:\s*(.*)$",
        flags=re.IGNORECASE,
    )

    current_key: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        nonlocal current_key, buffer
        if current_key is None:
            buffer = []
            return
        sections[current_key] = "\n".join(buffer).strip()
        buffer = []

    for line in summary_block.splitlines():
        match = key_pattern.match(line)
        if match:
            _flush()
            matched_key = key_lookup.get(match.group(1).strip().casefold())
            current_key = matched_key
            buffer = [match.group(2).rstrip()]
            continue
        if current_key is not None:
            buffer.append(line.rstrip())
    _flush()

    if not any(value for value in sections.values()):
        sections["Key findings and flow"] = summary_block.strip()
    return sections


def _render_big_questions(items: object) -> str:
    questions: list[dict] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                questions.append(item)
    if not questions:
        return "- (none)"

    output_lines: list[str] = []
    for item in questions:
        question = str(item.get("question", "(missing question)")).strip()
        why = str(item.get("why_important", item.get("why", "(missing rationale)"))).strip()
        related_papers = _wikilinks(_as_string_list(item.get("related_papers", [])))
        output_lines.append(f"- Question: {question}")
        output_lines.append(f"  - Why important: {why}")
        output_lines.append(f"  - Related papers: {related_papers}")
    return "\n".join(output_lines)


def _render_topic_big_questions(items: object) -> str:
    entries: list[dict] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                entries.append(item)
    if not entries:
        return "- (none)"

    output_lines: list[str] = []
    for item in entries:
        question = str(item.get("question", "(missing question)")).strip()
        why = str(item.get("why_important", item.get("why", "(missing rationale)"))).strip()
        related_papers = _wikilinks(_as_string_list(item.get("related_papers", [])))
        related_people = _wikilinks(_as_string_list(item.get("related_people", [])))
        output_lines.append(f"- Question: {question}")
        output_lines.append(f"  - Why important: {why}")
        output_lines.append(f"  - Related papers: {related_papers}")
        output_lines.append(f"  - Related people: {related_people}")
    return "\n".join(output_lines)


def render_paper_markdown(
    *,
    slug: str,
    paper_type: str,
    title: str,
    authors: list[str],
    corresponding_authors: list[str],
    journal: str,
    year: int,
    summary_block: str,
    related_topics: list[str],
) -> str:
    summary_sections = _extract_summary_sections(summary_block)
    people_links = _wikilinks(corresponding_authors)
    topic_links = _wikilinks(related_topics)
    author_line = ", ".join(f'"{author}"' for author in _dedupe(authors))
    header = (
        "---\n"
        f"slug: {slug}\n"
        "type: paper\n"
        f"paper_type: {_yaml_quoted(paper_type)}\n"
        f"title: {_yaml_quoted(title)}\n"
        f"authors: [{author_line}]\n"
        f"journal: {_yaml_quoted(journal)}\n"
        f"year: {year}\n"
        "---\n\n"
    )
    links_block = f"Corresponding authors: {people_links}\nRelated topics: {topic_links}\n\n"
    if paper_type == "review":
        body = (
            "## Key goal of the review\n"
            f"{summary_sections['Key goal of the review'] or '(missing)'}\n\n"
            "## Key unsolved questions\n"
            f"{summary_sections['Key unsolved questions'] or '(missing)'}\n\n"
            "## Why these unsolved questions are important\n"
            f"{summary_sections['Why these unsolved questions are important'] or '(missing)'}\n\n"
            "## Why these unsolved questions are still unsolved\n"
            f"{summary_sections['Why these unsolved questions are still unsolved'] or '(missing)'}\n\n"
        )
    else:
        body = (
            "## Key question solved\n"
            f"{summary_sections['Key question solved'] or '(missing)'}\n\n"
            "## Why this question is important\n"
            f"{summary_sections['Why this question is important'] or '(missing)'}\n\n"
            "## How the paper solves this question\n"
            f"{summary_sections['How the paper solves this question'] or '(missing)'}\n\n"
            "## Key findings and flow\n"
            f"{summary_sections['Key findings and flow'] or '(missing)'}\n\n"
            "## Limitations of the paper\n"
            f"{summary_sections['Limitations of the paper'] or '(missing)'}\n\n"
        )
    return (
        header
        + links_block
        + body
    )


def render_person_markdown(
    *,
    slug: str,
    name: str,
    email: str,
    affiliation: str,
    focus_areas: list[str],
    big_questions: object,
    related_papers: list[str],
    related_topics: list[str],
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: person\n"
        f"name: {_yaml_quoted(name)}\n"
        f"email: {_yaml_quoted(email)}\n"
        f"affiliation: {_yaml_quoted(affiliation)}\n"
        "---\n\n"
        "## Focus area\n"
        f"{chr(10).join(f'- {area}' for area in focus_areas) if focus_areas else '- (none)'}\n\n"
        "## Big questions\n"
        f"{_render_big_questions(big_questions)}\n\n"
        f"Related papers: {_wikilinks(related_papers)}\n"
        f"Related topics: {_wikilinks(related_topics)}\n"
    )


def render_topic_markdown(
    *,
    slug: str,
    topic: str,
    related_big_questions: object,
    related_papers: list[str],
    related_people: list[str],
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: topic\n"
        f"topic: {_yaml_quoted(topic)}\n"
        "---\n\n"
        "## Topic\n"
        f"- Topic: {topic}\n\n"
        "## Related big questions\n"
        f"{_render_topic_big_questions(related_big_questions)}\n\n"
        f"Related papers: {_wikilinks(related_papers)}\n"
        f"Related people: {_wikilinks(related_people)}\n"
    )


def render_index_markdown(*, paper_slugs: list[str], person_slugs: list[str], topic_slugs: list[str]) -> str:
    def _section(title: str, slugs: list[str]) -> str:
        deduped = _dedupe(slugs)
        if not deduped:
            return f"## {title}\n\n- (none)\n"
        lines = "\n".join(f"- [[{slug}]]" for slug in sorted(deduped))
        return f"## {title}\n\n{lines}\n"

    return (
        "# PaperBrain Index\n\n"
        + _section("Papers", paper_slugs)
        + "\n"
        + _section("People", person_slugs)
        + "\n"
        + _section("Topics", topic_slugs)
    )


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
