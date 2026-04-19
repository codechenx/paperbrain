from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from paperbrain.adapters.docling import DoclingParser
from paperbrain.models import ParsedPaper


@dataclass(slots=True)
class _MarkerConversionResult:
    markdown: str
    metadata: object
    title: str | None = None


class _MarkerConverterAdapter:
    def __init__(self, converter: object, text_from_rendered: object) -> None:
        self._converter = converter
        self._text_from_rendered = text_from_rendered

    def convert(self, file_path: str) -> _MarkerConversionResult:
        rendered = self._converter(file_path)
        markdown, _, _ = self._text_from_rendered(rendered)
        metadata = getattr(rendered, "metadata", None)
        title: str | None = None
        if isinstance(metadata, dict):
            candidate = metadata.get("title")
            if isinstance(candidate, str) and candidate.strip():
                title = candidate.strip()
        return _MarkerConversionResult(markdown=str(markdown), metadata=metadata, title=title)


class MarkerParser:
    def __init__(self) -> None:
        self._docling_parser = DoclingParser()

    def create_converter(self) -> object:
        try:
            pdf_module = import_module("marker.converters.pdf")
            models_module = import_module("marker.models")
            output_module = import_module("marker.output")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "marker-pdf is required for Marker parsing. Install it with `pip install marker-pdf`."
            ) from exc

        PdfConverter = getattr(pdf_module, "PdfConverter", None)
        create_model_dict = getattr(models_module, "create_model_dict", None)
        text_from_rendered = getattr(output_module, "text_from_rendered", None)
        if PdfConverter is None or create_model_dict is None or text_from_rendered is None:
            raise RuntimeError(
                "marker-pdf is required for Marker parsing. Install it with `pip install marker-pdf`."
            )

        converter = PdfConverter(artifact_dict=create_model_dict())
        return _MarkerConverterAdapter(converter=converter, text_from_rendered=text_from_rendered)

    def parse_pdf(self, path: Path) -> ParsedPaper:
        converter = self.create_converter()
        return self._docling_parser.parse_pdf_with_converter(path, converter)
