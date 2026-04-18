from dataclasses import dataclass
import importlib
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
        self._existing: set[tuple[str, str, int, tuple[str, ...], tuple[str, ...], str]] = set()
        self.upserts: list[tuple[str, bool]] = []
        self.replacements: list[tuple[str, list[str], list[list[float]]]] = []

    def has_source(self, source_path: str) -> bool:
        _ = source_path
        return False

    def has_paper(self, paper) -> bool:  # noqa: ANN001
        key = (
            paper.title,
            paper.journal,
            paper.year,
            tuple(paper.authors),
            tuple(paper.corresponding_authors),
            paper.full_text,
        )
        return key in self._existing

    def upsert_paper(self, paper, force: bool) -> str:  # noqa: ANN001
        self.upserts.append((paper.source_path, force))
        self._existing.add(
            (
                paper.title,
                paper.journal,
                paper.year,
                tuple(paper.authors),
                tuple(paper.corresponding_authors),
                paper.full_text,
            )
        )
        return "paper-1"

    def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        assert paper_id == "paper-1"
        assert not vectors or len(chunks) == len(vectors)
        self.replacements.append((paper_id, chunks, vectors))


class FakeParseWorker:
    def __init__(self, parser: FakeParser, close_calls: list[str]) -> None:
        self._parser = parser
        self._close_calls = close_calls

    def parse(self, path: Path) -> FakeParsedPaper:
        return self._parser.parse_pdf(path)

    def close(self) -> None:
        self._close_calls.append("closed")


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
    assert parser.calls == [paper_file, paper_file, paper_file]
    assert embeddings.calls == [["one two three", "four five six"], ["one two three", "four five six"]]
    assert repo.upserts == [(str(paper_file), False), (str(paper_file), True)]
    assert len(repo.replacements) == 2


def test_ingest_service_skips_existing_even_when_source_path_differs(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    service = IngestService(repo=repo, parser=parser, embeddings=embeddings, chunk_size_words=3)

    relative_file = tmp_path / "a.pdf"
    absolute_file = relative_file.resolve()
    relative_file.write_text("fake", encoding="utf-8")

    inserted1 = service.ingest_paths([str(relative_file)], force_all=False)
    inserted2 = service.ingest_paths([str(absolute_file)], force_all=False)

    assert inserted1 == 1
    assert inserted2 == 0
    assert len(repo.upserts) == 1
    assert len(repo.replacements) == 1


def test_ingest_service_ingests_without_embeddings(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    service = IngestService(repo=repo, parser=parser, embeddings=None, chunk_size_words=3)

    paper_file = tmp_path / "a.pdf"
    paper_file.write_text("fake", encoding="utf-8")

    inserted = service.ingest_paths([str(paper_file)], force_all=False)

    assert inserted == 1
    assert repo.upserts == [(str(paper_file), False)]
    assert repo.replacements == [("paper-1", ["one two three", "four five six"], [])]


def test_ingest_service_applies_start_offset_and_max_files(tmp_path: Path) -> None:
    repo = FakeRepo()

    class UniqueParser(FakeParser):
        def parse_pdf(self, path: Path) -> FakeParsedPaper:
            parsed = super().parse_pdf(path)
            return FakeParsedPaper(
                title=parsed.title,
                journal=parsed.journal,
                year=parsed.year,
                authors=parsed.authors,
                corresponding_authors=parsed.corresponding_authors,
                full_text=f"{parsed.full_text} {path.stem}",
                source_path=parsed.source_path,
            )

    parser = UniqueParser()
    embeddings = FakeEmbeddings()
    service = IngestService(repo=repo, parser=parser, embeddings=embeddings, chunk_size_words=3)

    paths: list[str] = []
    for name in ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]:
        pdf_path = tmp_path / name
        pdf_path.write_text("fake", encoding="utf-8")
        paths.append(str(pdf_path))

    inserted = service.ingest_paths(
        paths,
        force_all=False,
        start_offset=1,
        max_files=2,
        parse_worker_recycle_every=25,
    )

    assert inserted == 2
    assert [path.name for path in parser.calls] == ["b.pdf", "c.pdf"]


def test_ingest_service_recycles_parse_worker_after_threshold(tmp_path: Path) -> None:
    repo = FakeRepo()

    class UniqueParser(FakeParser):
        def parse_pdf(self, path: Path) -> FakeParsedPaper:
            parsed = super().parse_pdf(path)
            return FakeParsedPaper(
                title=parsed.title,
                journal=parsed.journal,
                year=parsed.year,
                authors=parsed.authors,
                corresponding_authors=parsed.corresponding_authors,
                full_text=f"{parsed.full_text} {path.stem}",
                source_path=parsed.source_path,
            )

    parser = UniqueParser()
    embeddings = FakeEmbeddings()
    close_calls: list[str] = []

    paths: list[str] = []
    for name in ["a.pdf", "b.pdf", "c.pdf"]:
        pdf_path = tmp_path / name
        pdf_path.write_text("fake", encoding="utf-8")
        paths.append(str(pdf_path))

    service = IngestService(
        repo=repo,
        parser=parser,
        embeddings=embeddings,
        chunk_size_words=3,
        parse_worker_factory=lambda: FakeParseWorker(parser, close_calls),
    )

    inserted = service.ingest_paths(paths, force_all=False, parse_worker_recycle_every=2)

    assert inserted == 3
    assert close_calls.count("closed") >= 2


def test_ingest_service_surfaces_worker_failure_with_file_context(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class BrokenWorker:
        def parse(self, path: Path) -> FakeParsedPaper:
            _ = path
            raise RuntimeError("worker crashed")

        def close(self) -> None:
            return None

    service = IngestService(
        repo=repo,
        parser=parser,
        embeddings=embeddings,
        chunk_size_words=3,
        parse_worker_factory=lambda: BrokenWorker(),
    )

    with pytest.raises(RuntimeError, match="worker crashed"):
        service.ingest_paths([str(pdf_path)], force_all=False, parse_worker_recycle_every=25)


def test_ingest_service_rejects_invalid_batch_arguments(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    service = IngestService(repo=repo, parser=parser, embeddings=embeddings, chunk_size_words=3)

    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    with pytest.raises(ValueError, match="start_offset"):
        service.ingest_paths([str(pdf_path)], force_all=False, start_offset=-1)
    with pytest.raises(ValueError, match="max_files"):
        service.ingest_paths([str(pdf_path)], force_all=False, max_files=-1)
    with pytest.raises(ValueError, match="parse_worker_recycle_every"):
        service.ingest_paths([str(pdf_path)], force_all=False, parse_worker_recycle_every=0)


def test_ingest_service_batches_embedding_requests(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    service = IngestService(
        repo=repo,
        parser=parser,
        embeddings=embeddings,
        chunk_size_words=1,
        embedding_batch_size=2,
    )

    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    inserted = service.ingest_paths([str(pdf_path)], force_all=False)

    assert inserted == 1
    assert embeddings.calls == [["one", "two"], ["three", "four"], ["five", "six"]]


def test_docling_parser_raises_for_missing_file(tmp_path: Path) -> None:
    parser = DoclingParser()
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        parser.parse_pdf(missing_pdf)


@pytest.mark.parametrize("ocr_enabled", [False, True])
def test_docling_parser_create_converter_respects_ocr_toggle(
    monkeypatch: pytest.MonkeyPatch, ocr_enabled: bool
) -> None:
    captured: dict[str, object] = {}

    class FakePipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = None

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: FakePipelineOptions) -> None:
            captured["do_ocr"] = pipeline_options.do_ocr
            self.pipeline_options = pipeline_options

    class FakeConverter:
        def __init__(self, *, format_options: object | None = None) -> None:
            captured["format_options"] = format_options

    class FakeInputFormat:
        PDF = "pdf-input-format"

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter
    document_converter_module.PdfFormatOption = FakePdfFormatOption
    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePipelineOptions
    base_models_module = types.ModuleType("docling.datamodel.base_models")
    base_models_module.InputFormat = FakeInputFormat

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel", types.ModuleType("docling.datamodel"))
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", base_models_module)

    converter = DoclingParser(ocr_enabled=ocr_enabled).create_converter()

    assert isinstance(converter, FakeConverter)
    assert captured["do_ocr"] is ocr_enabled
    assert captured["format_options"] is not None


def test_docling_parser_create_converter_supports_positional_only_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = None

    class FakePdfFormatOption:
        def __init__(self, pipeline_options: FakePipelineOptions, /) -> None:
            captured["do_ocr"] = pipeline_options.do_ocr
            self.pipeline_options = pipeline_options

    class FakeConverter:
        def __init__(self, format_options: object, /) -> None:
            captured["format_options"] = format_options

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter
    document_converter_module.PdfFormatOption = FakePdfFormatOption
    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePipelineOptions

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel", types.ModuleType("docling.datamodel"))
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module)

    converter = DoclingParser(ocr_enabled=True).create_converter()

    assert isinstance(converter, FakeConverter)
    assert captured["do_ocr"] is True
    assert captured["format_options"] is not None


def test_docling_parser_create_converter_propagates_pdf_option_type_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = None

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: FakePipelineOptions) -> None:
            _ = pipeline_options
            raise TypeError("pdf option constructor exploded")

    class FakeConverter:
        def __init__(self, *, format_options: object | None = None) -> None:
            _ = format_options

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter
    document_converter_module.PdfFormatOption = FakePdfFormatOption
    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePipelineOptions

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel", types.ModuleType("docling.datamodel"))
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module)

    with pytest.raises(TypeError, match="pdf option constructor exploded"):
        DoclingParser(ocr_enabled=True).create_converter()


def test_docling_parser_create_converter_propagates_converter_type_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_without_format_options = False

    class FakePipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = None

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: FakePipelineOptions) -> None:
            self.pipeline_options = pipeline_options

    class FakeConverter:
        def __init__(self, *, format_options: object | None = None) -> None:
            nonlocal called_without_format_options
            if format_options is None:
                called_without_format_options = True
                return
            raise TypeError("converter constructor exploded")

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter
    document_converter_module.PdfFormatOption = FakePdfFormatOption
    pipeline_options_module = types.ModuleType("docling.datamodel.pipeline_options")
    pipeline_options_module.PdfPipelineOptions = FakePipelineOptions

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel", types.ModuleType("docling.datamodel"))
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", pipeline_options_module)

    with pytest.raises(TypeError, match="converter constructor exploded"):
        DoclingParser(ocr_enabled=True).create_converter()
    assert called_without_format_options is False


def test_docling_parser_create_converter_falls_back_when_ocr_classes_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeConverter:
        def __init__(self, *, format_options: object | None = None) -> None:
            captured["format_options"] = format_options

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)

    converter = DoclingParser(ocr_enabled=True).create_converter()

    assert isinstance(converter, FakeConverter)
    assert captured["format_options"] is None


def test_docling_parser_create_converter_propagates_pipeline_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: object) -> None:
            _ = pipeline_options

    class FakeConverter:
        def __init__(self, *, format_options: object | None = None) -> None:
            _ = format_options

    docling_module = types.ModuleType("docling")
    document_converter_module = types.ModuleType("docling.document_converter")
    document_converter_module.DocumentConverter = FakeConverter
    document_converter_module.PdfFormatOption = FakePdfFormatOption
    datamodel_module = types.ModuleType("docling.datamodel")

    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.document_converter", document_converter_module)
    monkeypatch.setitem(sys.modules, "docling.datamodel", datamodel_module)

    def failing_import(module_name: str) -> types.ModuleType:
        if module_name == "docling.datamodel.pipeline_options":
            raise ImportError("pipeline init exploded")
        return importlib.import_module(module_name)

    monkeypatch.setattr("paperbrain.adapters.docling.import_module", failing_import)

    with pytest.raises(ImportError, match="pipeline init exploded"):
        DoclingParser(ocr_enabled=True).create_converter()


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


@pytest.mark.parametrize(
    "back_matter_heading",
    [
        "## Author contributions",
        "## Acknowledgements",
        "## Competing interests",
    ],
)
def test_docling_parser_trims_additional_back_matter_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, back_matter_heading: str
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    markdown = f"""
# Main Findings
This section should remain.
The discussion ends here.

{back_matter_heading}
Section body should be removed.
Trailing content should also be removed.
"""

    class FakeDocument:
        title = "Back Matter Trim Test"
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
    assert back_matter_heading not in parsed.full_text
    assert "Section body should be removed." not in parsed.full_text
    assert "Trailing content should also be removed." not in parsed.full_text


@pytest.mark.parametrize(
    ("first_back_matter_heading", "second_back_matter_heading"),
    [
        ("## Acknowledgements", "## References"),
        ("## References", "## Competing interests"),
    ],
)
def test_docling_parser_trims_from_earliest_back_matter_heading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_back_matter_heading: str,
    second_back_matter_heading: str,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    markdown = f"""
# Main Findings
This section should remain.
The discussion ends here.

{first_back_matter_heading}
First back-matter section body.

{second_back_matter_heading}
Second back-matter section body.
"""

    class FakeDocument:
        title = "Earliest Back Matter Trim Test"
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
    assert first_back_matter_heading not in parsed.full_text
    assert second_back_matter_heading not in parsed.full_text
    assert "First back-matter section body." not in parsed.full_text
    assert "Second back-matter section body." not in parsed.full_text
