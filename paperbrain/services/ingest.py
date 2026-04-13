from pathlib import Path
from typing import Protocol

from paperbrain.models import ParsedPaper
from paperbrain.utils import chunk_words


class IngestRepository(Protocol):
    def has_source(self, source_path: str) -> bool:
        ...

    def upsert_paper(self, paper: ParsedPaper, force: bool) -> str:
        ...

    def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        ...


class Parser(Protocol):
    def parse_pdf(self, path: Path) -> ParsedPaper:
        ...


class Embeddings(Protocol):
    def embed(self, chunks: list[str]) -> list[list[float]]:
        ...


class IngestService:
    def __init__(
        self,
        *,
        repo: IngestRepository,
        parser: Parser,
        embeddings: Embeddings,
        chunk_size_words: int = 200,
    ) -> None:
        self.repo = repo
        self.parser = parser
        self.embeddings = embeddings
        self.chunk_size_words = chunk_size_words

    def ingest_paths(self, paths: list[str], force_all: bool, recursive: bool = False) -> int:
        files = self._discover_files(paths, recursive=recursive)
        inserted = 0
        for file_path in files:
            source_path = str(file_path)
            if not force_all and self.repo.has_source(source_path):
                continue
            parsed = self.parser.parse_pdf(file_path)
            chunks = chunk_words(parsed.full_text, self.chunk_size_words)
            vectors = self.embeddings.embed(chunks)
            if len(chunks) != len(vectors):
                raise ValueError("Embedding count must match chunk count")
            paper_id = self.repo.upsert_paper(parsed, force=force_all)
            self.repo.replace_chunks(paper_id, chunks, vectors)
            inserted += 1
        return inserted

    @staticmethod
    def _discover_files(paths: list[str], recursive: bool) -> list[Path]:
        discovered: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            if path.is_file() and path.suffix.lower() == ".pdf":
                discovered.append(path)
                continue
            if path.is_dir():
                pattern = "**/*.pdf" if recursive else "*.pdf"
                discovered.extend(sorted(path.glob(pattern)))
        return discovered
