import pytest

from paperbrain.adapters.docling import DoclingParser
from paperbrain.adapters.markitdown import MarkItDownParser
from paperbrain.adapters.parser_factory import build_pdf_parser


def test_build_pdf_parser_returns_markitdown() -> None:
    parser = build_pdf_parser("markitdown", ocr_enabled=False)
    assert isinstance(parser, MarkItDownParser)


def test_build_pdf_parser_passes_ocr_enabled_to_markitdown_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_markitdown_parser(*args: object, **kwargs: object) -> object:
        calls.append((args, dict(kwargs)))
        return object()

    monkeypatch.setattr("paperbrain.adapters.parser_factory.MarkItDownParser", fake_markitdown_parser)

    build_pdf_parser("markitdown", ocr_enabled=True)

    assert calls == [((), {"ocr_enabled": True})]


def test_build_pdf_parser_returns_docling_with_ocr() -> None:
    parser = build_pdf_parser("docling", ocr_enabled=True)
    assert isinstance(parser, DoclingParser)
    assert parser.ocr_enabled is True


def test_build_pdf_parser_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="pdf_parser"):
        build_pdf_parser("invalid", ocr_enabled=False)
