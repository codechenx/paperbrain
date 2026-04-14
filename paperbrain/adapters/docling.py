from pathlib import Path
import re
from typing import Protocol

from paperbrain.models import ParsedPaper


class DoclingAdapter(Protocol):
    def parse_pdf(self, path: Path) -> ParsedPaper:
        ...


class DoclingParser:
    @staticmethod
    def _strip_image_payloads(markdown_content: str) -> str:
        cleaned = markdown_content.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"!\[[^\]]*]\([^)]+\)", "", cleaned)
        cleaned = re.sub(r"(?is)<img\b[^>]*>", "", cleaned)
        cleaned = re.sub(
            r"(?i)data:image/[a-z0-9.+-]+;base64,[a-z0-9+/=]+",
            "",
            cleaned,
        )
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _trim_references_section(markdown_content: str) -> str:
        atx_heading = re.search(
            r"(?im)^[ \t]{0,3}#{1,6}[ \t]+(?:references|bibliography|works[ \t]+cited)\b[^\n]*$",
            markdown_content,
        )
        setext_heading = re.search(
            r"(?im)^[ \t]*(?:references|bibliography|works[ \t]+cited)[ \t]*\n[ \t]*[-=]{2,}[ \t]*$",
            markdown_content,
        )
        starts = [match.start() for match in (atx_heading, setext_heading) if match]
        if not starts:
            return markdown_content.strip()
        return markdown_content[: min(starts)].rstrip()

    @staticmethod
    def _extract_first_page_text(document: object, markdown_content: str) -> str:
        texts = getattr(document, "texts", None)
        if isinstance(texts, list):
            parts: list[str] = []
            for item in texts:
                text = getattr(item, "text", None)
                prov = getattr(item, "prov", None)
                if not isinstance(text, str) or not text.strip() or not isinstance(prov, list):
                    continue
                if any(getattr(region, "page_no", None) == 1 for region in prov):
                    parts.append(text.strip())
            first_page_text = "\n".join(parts).strip()
            if first_page_text:
                return first_page_text
        # Fallback: the markdown export is page-ordered, so the prefix approximates page 1.
        return markdown_content[:4000].strip()

    @staticmethod
    def _extract_corresponding_authors_from_first_page(first_page_text: str) -> list[str]:
        email_pattern = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        seen: set[str] = set()
        authors: list[str] = []
        for line in first_page_text.splitlines():
            lowered = line.casefold()
            if "correspond" not in lowered and "e-mail" not in lowered and "email" not in lowered:
                continue
            for email in email_pattern.findall(line):
                normalized = email.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    authors.append(normalized)
        if authors:
            return authors
        for email in email_pattern.findall(first_page_text):
            normalized = email.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                authors.append(normalized)
        return authors

    @staticmethod
    def _infer_journal_from_first_page(first_page_text: str) -> str | None:
        labeled = re.search(
            r"(?im)^\s*(?:journal|publication|published in)\s*[:\-]\s*(.+)$",
            first_page_text,
        )
        if labeled:
            return labeled.group(1).strip()

        # Common title-line journals visible on page 1.
        keyword = re.search(
            r"(?im)\b(nature(?:\s+[a-z][a-z\- ]+)?|science|cell(?:\s+[a-z][a-z\- ]+)?|the lancet(?:\s+[a-z][a-z\- ]+)?)\b",
            first_page_text,
        )
        if keyword:
            return " ".join(part.capitalize() for part in keyword.group(1).split())
        return None

    @staticmethod
    def _infer_authors_from_first_page(first_page_text: str) -> list[str]:
        lines = [line.strip() for line in first_page_text.splitlines() if line.strip()]
        name_pattern = re.compile(r"[A-Z][a-zA-Z'`\-]+(?:\s+[A-Z](?:\.)?)?(?:\s+[A-Z][a-zA-Z'`\-]+)+")
        for line in lines[:20]:
            candidate = re.sub(r"\b\d+\b", " ", line)
            candidate = " ".join(candidate.split())
            if len(candidate) < 8 or len(candidate) > 240:
                continue
            if "@" in candidate or "http" in candidate.casefold():
                continue
            names = [name.strip() for name in name_pattern.findall(candidate)]
            seen: set[str] = set()
            deduped: list[str] = []
            for name in names:
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(name)
            if len(deduped) >= 2:
                return deduped
        return []

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
        content = self._strip_image_payloads(content)
        content = self._trim_references_section(content)
        first_page_text = self._extract_first_page_text(document, content)

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
        )
        if not journal:
            journal = self._infer_journal_from_first_page(first_page_text)
        if not journal:
            journal = "Unknown Journal"
        year = _coerce_year(
            _get_value(doc_metadata, "year")
            or _get_value(doc_metadata, "publication_year")
            or _get_value(result_metadata, "year")
            or _get_value(result_metadata, "publication_year")
        )
        if not year:
            year = _coerce_year(first_page_text)
        authors = _coerce_authors(
            _get_value(doc_metadata, "authors")
            or _get_value(doc_metadata, "author")
            or _get_value(result_metadata, "authors")
            or _get_value(result_metadata, "author")
        )
        if not authors:
            authors = self._infer_authors_from_first_page(first_page_text)
        corresponding_authors = _coerce_authors(
            _get_value(doc_metadata, "corresponding_authors")
            or _get_value(result_metadata, "corresponding_authors")
        )
        if not corresponding_authors:
            corresponding_authors = self._extract_corresponding_authors_from_first_page(first_page_text)

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
