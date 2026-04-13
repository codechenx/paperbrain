from pathlib import Path
import re
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

        def _get_value(source: object, key: str) -> object:
            if source is None:
                return None
            if isinstance(source, dict):
                return source.get(key)
            return getattr(source, key, None)

        def _first_text(*values: object) -> str | None:
            for value in values:
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            return None

        def _coerce_authors(value: object) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                normalized = value.strip()
                return [normalized] if normalized else []
            if isinstance(value, list):
                authors: list[str] = []
                for item in value:
                    if isinstance(item, dict):
                        candidate = _first_text(item.get("name"), item.get("full_name"), item.get("author"))
                    else:
                        candidate = _first_text(item)
                    if candidate:
                        authors.append(candidate)
                return authors
            return []

        def _coerce_year(value: object) -> int | None:
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                match = re.search(r"\b(19|20)\d{2}\b", value)
                if match:
                    return int(match.group(0))
            return None

        doc_metadata = _get_value(document, "metadata")
        result_metadata = _get_value(result, "metadata")
        title = _first_text(
            _get_value(document, "title"),
            _get_value(doc_metadata, "title"),
            _get_value(result, "title"),
            _get_value(result_metadata, "title"),
            path.stem,
        )
        journal = _first_text(
            _get_value(doc_metadata, "journal"),
            _get_value(doc_metadata, "publication"),
            _get_value(result_metadata, "journal"),
            _get_value(result_metadata, "publication"),
            "Unknown Journal",
        )
        year = _coerce_year(
            _get_value(doc_metadata, "year")
            or _get_value(doc_metadata, "publication_year")
            or _get_value(result_metadata, "year")
            or _get_value(result_metadata, "publication_year")
        )
        authors = _coerce_authors(
            _get_value(doc_metadata, "authors")
            or _get_value(doc_metadata, "author")
            or _get_value(result_metadata, "authors")
            or _get_value(result_metadata, "author")
        )
        corresponding_authors = _coerce_authors(
            _get_value(doc_metadata, "corresponding_authors")
            or _get_value(result_metadata, "corresponding_authors")
        )

        return ParsedPaper(
            title=title or path.stem,
            journal=journal or "Unknown Journal",
            year=year or 1970,
            authors=authors,
            corresponding_authors=corresponding_authors,
            full_text=content.strip(),
            source_path=str(path),
        )


DefaultDoclingAdapter = DoclingParser
