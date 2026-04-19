from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.marker import MarkerParser
from paperbrain.config import normalize_pdf_parser
from paperbrain.services.ingest import Parser


def build_pdf_parser(pdf_parser: str, *, docling_ocr_enabled: bool) -> Parser:
    normalized = normalize_pdf_parser(pdf_parser)
    if normalized == "marker":
        return MarkerParser()
    if normalized == "docling":
        return DoclingParser(ocr_enabled=docling_ocr_enabled)
    raise ValueError("Invalid pdf_parser in configuration file. Allowed values: docling, marker")
