from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.markitdown import MarkItDownParser
from paperbrain.config import normalize_pdf_parser
from paperbrain.services.ingest import Parser


def build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool) -> Parser:
    normalized = normalize_pdf_parser(pdf_parser)
    if normalized == "markitdown":
        return MarkItDownParser(ocr_enabled=ocr_enabled)
    if normalized == "docling":
        return DoclingParser(ocr_enabled=ocr_enabled)
    raise ValueError("Invalid pdf_parser in configuration file. Allowed values: docling, markitdown")
