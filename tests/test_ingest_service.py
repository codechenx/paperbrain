from dataclasses import dataclass
from pathlib import Path
import sys
import types

import pytest

from paperbrain.adapters.docling import DoclingParser
from paperbrain.services.ingest import IngestService


@dataclass
class FakeParsedPaper:
    title: str
    journal: str
    year: int
    authors: list[str]
    corresponding_authors: list[str]
    full_text: str
    source_path: str


class FakeParser:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def parse_pdf(self, path: Path) -> FakeParsedPaper:
        self.calls.append(path)
        return FakeParsedPaper(
            title="P53 Study",
            journal="Nature",
            year=2024,
            authors=["Alice", "Bob"],
            corresponding_authors=["Alice <alice@uni.edu>"],
            full_text="one two three four five six",
            source_path=str(path),
        )


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, chunks: list[str]) -> list[list[float]]:
        self.calls.append(chunks)
        return [[0.1, 0.2, 0.3] for _ in chunks]


class FakeRepo:
    def __init__(self) -> None:
        self._existing: set[str] = set()
        self.upserts: list[tuple[str, bool]] = []
        self.replacements: list[tuple[str, list[str], list[list[float]]]] = []

    def has_source(self, source_path: str) -> bool:
        return source_path in self._existing

    def upsert_paper(self, paper, force: bool) -> str:  # noqa: ANN001
        self.upserts.append((paper.source_path, force))
        self._existing.add(paper.source_path)
        return "paper-1"

    def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        assert paper_id == "paper-1"
        assert len(chunks) == len(vectors)
        self.replacements.append((paper_id, chunks, vectors))


def test_ingest_service_skips_existing_without_force(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    service = IngestService(repo=repo, parser=parser, embeddings=embeddings, chunk_size_words=3)

    paper_file = tmp_path / "a.pdf"
    paper_file.write_text("fake", encoding="utf-8")

    inserted1 = service.ingest_paths([str(paper_file)], force_all=False)
    inserted2 = service.ingest_paths([str(paper_file)], force_all=False)
    inserted3 = service.ingest_paths([str(paper_file)], force_all=True)

    assert inserted1 == 1
    assert inserted2 == 0
    assert inserted3 == 1
    assert parser.calls == [paper_file, paper_file]
    assert embeddings.calls == [["one two three", "four five six"], ["one two three", "four five six"]]
    assert repo.upserts == [(str(paper_file), False), (str(paper_file), True)]
    assert len(repo.replacements) == 2


def test_docling_parser_raises_for_missing_file(tmp_path: Path) -> None:
    parser = DoclingParser()
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        parser.parse_pdf(missing_pdf)


def test_docling_parser_extracts_structured_metadata_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeDocument:
        title = "Structured title"
        metadata = {
            "authors": ["Alice Example", "Bob Example"],
            "year": "2024",
            "journal": "Nature",
        }

        def export_to_markdown(self) -> str:
            return "# heading\n\nbody"

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert parsed.title == "Structured title"
    assert parsed.authors == ["Alice Example", "Bob Example"]
    assert parsed.year == 2024
    assert parsed.journal == "Nature"
    assert parsed.full_text == "# heading\n\nbody"
    assert parsed.source_path == str(pdf_path)


def test_docling_parser_falls_back_to_defaults_when_metadata_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "untitled.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeDocument:
        metadata = {}

        def export_to_markdown(self) -> str:
            return "body"

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert parsed.title == "untitled"
    assert parsed.authors == []
    assert parsed.year == 1970
    assert parsed.journal == "Unknown Journal"


def test_docling_parser_infers_corresponding_authors_and_journal_from_first_page_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeProv:
        def __init__(self, page_no: int) -> None:
            self.page_no = page_no

    class FakeTextItem:
        def __init__(self, text: str, page_no: int) -> None:
            self.text = text
            self.prov = [FakeProv(page_no)]

    class FakeDocument:
        title = "First-page Metadata Test"
        metadata = {}
        texts = [
            FakeTextItem("Nature Microbiology", 1),
            FakeTextItem("Corresponding author: junyu@cuhk.edu.hk", 1),
            FakeTextItem("page two content", 2),
        ]

        def export_to_markdown(self) -> str:
            return "body"

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert parsed.journal == "Nature Microbiology"
    assert parsed.corresponding_authors == ["junyu@cuhk.edu.hk"]


def test_docling_parser_removes_image_payload_but_keeps_caption_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    markdown = """
# Results
![Figure 1 embed](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA)
<img src="data:image/png;base64,QUJDREVGRw==" alt="Figure 2 embed" />
Supplementary payload: data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD

Figure 1. p53 staining intensity in treated cells.
Legend: Blue bars indicate controls.
"""

    class FakeDocument:
        title = "Image Payload Test"
        metadata = {}

        def export_to_markdown(self) -> str:
            return markdown

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert "![Figure 1 embed]" not in parsed.full_text
    assert "<img" not in parsed.full_text
    assert "data:image/png;base64" not in parsed.full_text
    assert "data:image/jpeg;base64" not in parsed.full_text
    assert "Figure 1. p53 staining intensity in treated cells." in parsed.full_text
    assert "Legend: Blue bars indicate controls." in parsed.full_text


def test_docling_parser_removes_newline_wrapped_data_image_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    markdown = """
# Results
Wrapped payload:
data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA
AAABCAIAAACQd1Pe==

Valid text should remain.
"""

    class FakeDocument:
        title = "Wrapped Payload Test"
        metadata = {}

        def export_to_markdown(self) -> str:
            return markdown

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert "data:image/png;base64" not in parsed.full_text
    assert "iVBORw0KGgoAAAANSUhEUgAAAAUA" not in parsed.full_text
    assert "AAABCAIAAACQd1Pe==" not in parsed.full_text
    assert "Valid text should remain." in parsed.full_text


@pytest.mark.parametrize(
    "references_heading",
    ["## References", "## Bibliography", "## Works Cited", "References"],
)
def test_docling_parser_trims_references_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, references_heading: str
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    markdown = f"""
# Main Findings
This section should remain.
The discussion ends here.

{references_heading}
[1] Example, A. et al. 2021.
[2] Example, B. et al. 2022.
"""

    class FakeDocument:
        title = "References Trim Test"
        metadata = {}

        def export_to_markdown(self) -> str:
            return markdown

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert "This section should remain." in parsed.full_text
    assert "The discussion ends here." in parsed.full_text
    assert references_heading not in parsed.full_text
    assert "[1] Example, A. et al. 2021." not in parsed.full_text
    assert "[2] Example, B. et al. 2022." not in parsed.full_text
