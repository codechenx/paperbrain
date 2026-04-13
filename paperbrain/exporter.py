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


def render_paper_markdown(
    *,
    slug: str,
    title: str,
    authors: list[str],
    corresponding_authors: list[str],
    journal: str,
    year: int,
    summary_block: str,
    related_topics: list[str],
) -> str:
    people_links = _wikilinks(corresponding_authors)
    topic_links = _wikilinks(related_topics)
    author_line = ", ".join(f'"{author}"' for author in _dedupe(authors))
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: paper\n"
        f'title: "{title}"\n'
        f"authors: [{author_line}]\n"
        f"journal: {journal}\n"
        f"year: {year}\n"
        "---\n\n"
        f"Corresponding authors: {people_links}\n"
        f"Related topics: {topic_links}\n\n"
        "<!-- paperbrain_paper_summary:start -->\n"
        f"{summary_block}\n"
        "<!-- paperbrain_paper_summary:end -->\n"
    )


def render_person_markdown(
    *,
    slug: str,
    name: str,
    related_papers: list[str],
    related_topics: list[str],
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: person\n"
        f'name: "{name}"\n'
        "---\n\n"
        f"Related papers: {_wikilinks(related_papers)}\n"
        f"Related topics: {_wikilinks(related_topics)}\n"
    )


def render_topic_markdown(
    *,
    slug: str,
    topic: str,
    related_papers: list[str],
    related_people: list[str],
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: topic\n"
        f'topic: "{topic}"\n'
        "---\n\n"
        f"Related papers: {_wikilinks(related_papers)}\n"
        f"Related people: {_wikilinks(related_people)}\n"
    )


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
