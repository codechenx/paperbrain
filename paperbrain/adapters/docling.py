from pathlib import Path
from typing import Protocol

from paperbrain.models import ParsedPaper


class DoclingAdapter(Protocol):
    def parse_pdf(self, path: Path) -> ParsedPaper:
        ...


class DefaultDoclingAdapter:
    def parse_pdf(self, path: Path) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        title = path.stem.replace("_", " ").strip() or "Untitled Paper"
        content = path.read_bytes().decode("latin-1", errors="ignore")
        return ParsedPaper(
            title=title,
            journal="Unknown Journal",
            year=1970,
            authors=[],
            corresponding_authors=[],
            full_text=content.strip(),
            source_path=str(path),
        )

