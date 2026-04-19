from pathlib import Path
import types

import pytest

from paperbrain.adapters.marker import MarkerParser


def test_marker_parser_raises_when_marker_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    def fake_import_module(name: str) -> object:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.marker.import_module", fake_import_module)

    parser = MarkerParser()
    with pytest.raises(RuntimeError, match="marker-pdf"):
        parser.parse_pdf(pdf_path)


def test_marker_parser_passes_force_ocr_true_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakePdfConverter:
        def __init__(
            self, artifact_dict: dict[str, str], config: dict[str, object] | None = None
        ) -> None:
            _ = artifact_dict
            captured["config"] = config

        def __call__(self, file_path: str) -> dict[str, str]:
            return {"path": file_path}

    def fake_create_model_dict() -> dict[str, str]:
        return {"ok": "yes"}

    def fake_text_from_rendered(rendered: object) -> tuple[str, dict[str, str], dict[str, str]]:
        _ = rendered
        return "Nature\nPublished 2024\n", {}, {}

    pdf_module = types.SimpleNamespace(PdfConverter=FakePdfConverter)
    models_module = types.SimpleNamespace(create_model_dict=fake_create_model_dict)
    output_module = types.SimpleNamespace(text_from_rendered=fake_text_from_rendered)

    def fake_import_module(name: str) -> object:
        if name == "marker.converters.pdf":
            return pdf_module
        if name == "marker.models":
            return models_module
        if name == "marker.output":
            return output_module
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.marker.import_module", fake_import_module)

    MarkerParser(ocr_enabled=True).parse_pdf(pdf_path)
    assert captured["config"] == {"force_ocr": True}


def test_marker_parser_does_not_force_ocr_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakePdfConverter:
        def __init__(
            self, artifact_dict: dict[str, str], config: dict[str, object] | None = None
        ) -> None:
            _ = artifact_dict
            captured["config"] = config

        def __call__(self, file_path: str) -> dict[str, str]:
            return {"path": file_path}

    def fake_create_model_dict() -> dict[str, str]:
        return {"ok": "yes"}

    def fake_text_from_rendered(rendered: object) -> tuple[str, dict[str, str], dict[str, str]]:
        _ = rendered
        return "Nature\nPublished 2024\n", {}, {}

    pdf_module = types.SimpleNamespace(PdfConverter=FakePdfConverter)
    models_module = types.SimpleNamespace(create_model_dict=fake_create_model_dict)
    output_module = types.SimpleNamespace(text_from_rendered=fake_text_from_rendered)

    def fake_import_module(name: str) -> object:
        if name == "marker.converters.pdf":
            return pdf_module
        if name == "marker.models":
            return models_module
        if name == "marker.output":
            return output_module
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.marker.import_module", fake_import_module)

    MarkerParser(ocr_enabled=False).parse_pdf(pdf_path)
    assert captured["config"] in (None, {})


def test_marker_parser_returns_normalized_parsed_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakePdfConverter:
        def __init__(self, artifact_dict: dict[str, str]) -> None:
            self.artifact_dict = artifact_dict

        def __call__(self, file_path: str) -> dict[str, str]:
            return {"path": file_path}

    def fake_create_model_dict() -> dict[str, str]:
        return {"ok": "yes"}

    def fake_text_from_rendered(rendered: object) -> tuple[str, dict[str, str], dict[str, str]]:
        _ = rendered
        text = (
            "Nature Medicine\n"
            "Alice Example Bob Example\n"
            "Corresponding author: alice@example.com\n"
            "Published 2024\n"
        )
        return text, {}, {}

    pdf_module = types.SimpleNamespace(PdfConverter=FakePdfConverter)
    models_module = types.SimpleNamespace(create_model_dict=fake_create_model_dict)
    output_module = types.SimpleNamespace(text_from_rendered=fake_text_from_rendered)

    def fake_import_module(name: str) -> object:
        if name == "marker.converters.pdf":
            return pdf_module
        if name == "marker.models":
            return models_module
        if name == "marker.output":
            return output_module
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr("paperbrain.adapters.marker.import_module", fake_import_module)

    parsed = MarkerParser().parse_pdf(pdf_path)
    assert parsed.title == "paper"
    assert parsed.journal == "Nature Medicine"
    assert parsed.year == 2024
    assert parsed.source_path == str(pdf_path)
    assert parsed.corresponding_authors == ["alice@example.com"]
    assert parsed.full_text.startswith("Nature Medicine")


def test_marker_parser_parse_pdf_with_converter_reuses_converter(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConverter:
        def convert(self, file_path: str):  # noqa: ANN201
            class Result:
                document = None
                markdown = (
                    "Nature Medicine\n"
                    "Published 2024\n"
                    "Alice Example Bob Example\n"
                    "Corresponding author: alice@example.com"
                )
                metadata = {}

            assert file_path == str(pdf_path)
            return Result()

    parser = MarkerParser(ocr_enabled=False)
    parsed = parser.parse_pdf_with_converter(pdf_path, FakeConverter())
    assert parsed.title == "paper"
    assert parsed.year == 2024
