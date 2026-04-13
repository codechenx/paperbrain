import re
import unicodedata


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def normalize_email(raw: str) -> str:
    value = raw.strip().lower()
    if "<" in value and ">" in value:
        start = value.index("<") + 1
        end = value.index(">")
        value = value[start:end]
    return value


def chunk_words(text: str, chunk_size_words: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    chunks: list[str] = []
    for i in range(0, len(words), max(1, chunk_size_words)):
        chunks.append(" ".join(words[i : i + max(1, chunk_size_words)]))
    return chunks

