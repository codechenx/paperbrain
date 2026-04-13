from pathlib import Path


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
    people_links = ", ".join(f"[[{x}]]" for x in corresponding_authors) if corresponding_authors else "None"
    topic_links = ", ".join(f"[[{x}]]" for x in related_topics) if related_topics else "None"
    author_line = ", ".join(authors) if authors else "Unknown"
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


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

