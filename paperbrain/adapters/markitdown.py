from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from paperbrain.adapters.docling import DoclingParser
from paperbrain.models import ParsedPaper


@dataclass(slots=True)
class _MarkItDownConversionResult:
    markdown: str
    metadata: object
    title: str | None = None


class _MarkItDownConverterAdapter:
    def __init__(self, converter: object) -> None:
        self._converter = converter

    @staticmethod
    def _pick_text(result: object) -> str:
        for attr in ("text_content", "markdown", "text"):
            value = getattr(result, attr, None)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return str(result)

    @staticmethod
    def _pick_title(result: object, metadata: object) -> str | None:
        title = getattr(result, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()
        if isinstance(metadata, dict):
            candidate = metadata.get("title")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def convert(self, file_path: str) -> _MarkItDownConversionResult:
        result = self._converter.convert(file_path)
        metadata = getattr(result, "metadata", None)
        return _MarkItDownConversionResult(
            markdown=self._pick_text(result),
            metadata=metadata,
            title=self._pick_title(result, metadata),
        )


class MarkItDownParser:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        self.ocr_enabled = ocr_enabled
        self._docling_parser = DoclingParser()

    def create_converter(self) -> object:
        try:
            markitdown_module = import_module("markitdown")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "markitdown is required for PDF parsing. Install it with `pip install 'markitdown[pdf]'`."
            ) from exc

        if self.ocr_enabled:
            try:
                import_module("markitdown_ocr")
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "OCR for markitdown requires `markitdown-ocr`. Install it, or set ocr_enabled=false."
                ) from exc

        markitdown_type = getattr(markitdown_module, "MarkItDown", None)
        if markitdown_type is None:
            raise RuntimeError("markitdown installation is invalid: MarkItDown class is missing.")

        converter_kwargs: dict[str, object] = {}
        if self.ocr_enabled:
            converter_kwargs["enable_plugins"] = True
        try:
            converter = markitdown_type(**converter_kwargs)
        except TypeError as exc:
            if self.ocr_enabled:
                raise RuntimeError(
                    "OCR is enabled, but this markitdown version does not support "
                    "`enable_plugins`. Upgrade `markitdown[pdf]`/`markitdown-ocr`, "
                    "or set ocr_enabled=false."
                ) from exc
            converter = markitdown_type()
        return _MarkItDownConverterAdapter(converter)

    def parse_pdf(self, path: Path) -> ParsedPaper:
        converter = self.create_converter()
        return self.parse_pdf_with_converter(path, converter)

    def parse_pdf_with_converter(self, path: Path, converter: object) -> ParsedPaper:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        return self._docling_parser.parse_pdf_with_converter(path, converter)
