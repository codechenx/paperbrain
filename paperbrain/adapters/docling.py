from pathlib import Path
from typing import Protocol

from paperbrain.models import ParsedPaper


class DoclingAdapter(Protocol):
    def parse_pdf(self, path: Path) -> ParsedPaper:
        ...


class DoclingParser:
    def parse_pdf(self, path: Path) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        try:
            from docling.document_converter import DocumentConverter
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "docling is required for PDF parsing. Install it with `pip install docling`."
            ) from exc

        converter = DocumentConverter()
        result = converter.convert(str(path))
        document = getattr(result, "document", None)
        if document is not None and hasattr(document, "export_to_markdown"):
            content = document.export_to_markdown()
        elif hasattr(result, "markdown"):
            content = str(result.markdown)
        else:
            content = str(result)
        title = getattr(document, "title", None) or path.stem.replace("_", " ").strip() or "Untitled Paper"
        return ParsedPaper(
            title=title,
            journal="Unknown Journal",
            year=1970,
            authors=[],
            corresponding_authors=[],
            full_text=content.strip(),
            source_path=str(path),
        )


DefaultDoclingAdapter = DoclingParser
