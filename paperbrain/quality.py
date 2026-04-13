import re


def normalize_whitespace(text: str) -> str:
    collapsed = " ".join(text.split())
    return f"{collapsed}\n"


def remove_dead_links(text: str, known_slugs: set[str]) -> str:
    pattern = re.compile(r"\[\[([^\]]+)\]\]")
    output = text
    for match in pattern.findall(text):
        if match not in known_slugs:
            output = output.replace(f"[[{match}]]", match)
    return output

