import re

_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
_INLINE_WHITESPACE = re.compile(r"[ \t]+")
_LEADING_WHITESPACE = re.compile(r"^[ \t]*")


def normalize_whitespace(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized_lines: list[str] = []
    previous_blank = False

    for line in lines:
        if not line.strip():
            if normalized_lines and not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue

        rstripped = line.rstrip(" \t")
        leading = _LEADING_WHITESPACE.match(rstripped).group(0)
        content = rstripped[len(leading) :]
        normalized_lines.append(f"{leading}{_INLINE_WHITESPACE.sub(' ', content)}")
        previous_blank = False

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()

    return "\n".join(normalized_lines) + "\n"


def remove_dead_links(text: str, known_slugs: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        if target in known_slugs:
            return match.group(0)
        return target

    return _LINK_PATTERN.sub(replace, text)


def ensure_frontmatter_fields(text: str, defaults: dict[str, str]) -> str:
    if not text.startswith("---\n"):
        return text

    marker = "\n---\n"
    end = text.find(marker, 4)
    if end < 0:
        return text

    header = text[4:end]
    body = text[end + len(marker) :]
    lines = header.split("\n") if header else []
    existing_keys = {
        line.split(":", 1)[0].strip()
        for line in lines
        if ":" in line and line.split(":", 1)[0].strip()
    }

    for key, value in defaults.items():
        if key not in existing_keys:
            lines.append(f"{key}: {value}")

    return "---\n" + "\n".join(lines) + "\n---\n" + body
