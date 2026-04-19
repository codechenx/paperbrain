from pathlib import Path
import types

import pytest

from paperbrain.adapters.markitdown import MarkItDownParser


def test_markitdown_parser_raises_when_markitdown_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    def fake_import_module(name: str) -> object:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.markitdown.import_module", fake_import_module)

    parser = MarkItDownParser()
    with pytest.raises(RuntimeError, match=r"markitdown\[pdf\]"):
        parser.parse_pdf(pdf_path)


def test_markitdown_parser_requires_ocr_plugin_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMarkItDown:
        def __init__(self, **_kwargs: object) -> None:
            return None

    markitdown_module = types.SimpleNamespace(MarkItDown=FakeMarkItDown)

    def fake_import_module(name: str) -> object:
        if name == "markitdown":
            return markitdown_module
        if name == "markitdown_ocr":
            raise ModuleNotFoundError(name=name)
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.markitdown.import_module", fake_import_module)

    with pytest.raises(RuntimeError, match="markitdown-ocr"):
        MarkItDownParser(ocr_enabled=True).create_converter()


def test_markitdown_parser_create_converter_enables_plugins_for_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def convert(self, _file_path: str) -> object:
            return types.SimpleNamespace(text_content="Published 2024", metadata={})

    markitdown_module = types.SimpleNamespace(MarkItDown=FakeMarkItDown)

    def fake_import_module(name: str) -> object:
        if name == "markitdown":
            return markitdown_module
        if name == "markitdown_ocr":
            return object()
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.markitdown.import_module", fake_import_module)

    MarkItDownParser(ocr_enabled=True).create_converter()
    assert captured["kwargs"] == {"enable_plugins": True}


def test_markitdown_parser_returns_normalized_parsed_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeMarkItDown:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def convert(self, file_path: str) -> object:
            assert file_path == str(pdf_path)
            text = (
                "Nature Medicine\n"
                "Alice Example Bob Example\n"
                "Corresponding author: alice@example.com\n"
                "Published 2024\n"
            )
            return types.SimpleNamespace(text_content=text, metadata={})

    markitdown_module = types.SimpleNamespace(MarkItDown=FakeMarkItDown)

    def fake_import_module(name: str) -> object:
        if name == "markitdown":
            return markitdown_module
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.markitdown.import_module", fake_import_module)

    parsed = MarkItDownParser().parse_pdf(pdf_path)
    assert parsed.title == "paper"
    assert parsed.journal == "Nature Medicine"
    assert parsed.year == 2024
    assert parsed.source_path == str(pdf_path)
    assert parsed.corresponding_authors == ["alice@example.com"]
    assert parsed.full_text.startswith("Nature Medicine")


def test_markitdown_parser_parse_pdf_with_converter_reuses_converter(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConverter:
        def convert(self, file_path: str) -> object:
            assert file_path == str(pdf_path)
            text = (
                "Nature Medicine\n"
                "Published 2024\n"
                "Alice Example Bob Example\n"
                "Corresponding author: alice@example.com"
            )
            return types.SimpleNamespace(text_content=text, metadata={})

    parser = MarkItDownParser(ocr_enabled=False)
    parsed = parser.parse_pdf_with_converter(pdf_path, FakeConverter())
    assert parsed.title == "paper"
    assert parsed.year == 2024
