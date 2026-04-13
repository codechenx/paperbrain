from dataclasses import dataclass
from pathlib import Path

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
    def parse_pdf(self, path: Path) -> FakeParsedPaper:
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
    def embed(self, chunks: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in chunks]


class FakeRepo:
    def __init__(self) -> None:
        self._existing: set[str] = set()

    def has_source(self, source_path: str) -> bool:
        return source_path in self._existing

    def upsert_paper(self, paper, force: bool) -> str:  # noqa: ANN001
        self._existing.add(paper.source_path)
        return "paper-1"

    def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        assert paper_id == "paper-1"
        assert len(chunks) == len(vectors)


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

