from paperbrain.quality import normalize_whitespace, remove_dead_links


def lint_markdown(text: str, known_slugs: set[str]) -> str:
    cleaned = normalize_whitespace(text)
    return remove_dead_links(cleaned, known_slugs)

