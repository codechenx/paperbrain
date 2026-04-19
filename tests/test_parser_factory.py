import pytest

from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.marker import MarkerParser
from paperbrain.adapters.parser_factory import build_pdf_parser


def test_build_pdf_parser_returns_marker() -> None:
    parser = build_pdf_parser("marker", ocr_enabled=False)
    assert isinstance(parser, MarkerParser)


def test_build_pdf_parser_returns_docling_with_ocr() -> None:
    parser = build_pdf_parser("docling", ocr_enabled=True)
    assert isinstance(parser, DoclingParser)
    assert parser.ocr_enabled is True


def test_build_pdf_parser_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="pdf_parser"):
        build_pdf_parser("invalid", ocr_enabled=False)
