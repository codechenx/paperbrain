from dataclasses import dataclass
from pathlib import Path

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
