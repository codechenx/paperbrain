from pathlib import Path
from typing import Callable, Protocol

from paperbrain.models import ParsedPaper
from paperbrain.utils import chunk_words


class IngestRepository(Protocol):
    def has_source(self, source_path: str) -> bool:
        ...

    def has_paper(self, paper: ParsedPaper) -> bool:
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


class ParseWorker(Protocol):
    def parse(self, path: Path) -> ParsedPaper:
        ...

    def close(self) -> None:
        ...


class _InlineParseWorker:
    def __init__(self, parser: Parser) -> None:
        self._parser = parser

    def parse(self, path: Path) -> ParsedPaper:
        return self._parser.parse_pdf(path)

    def close(self) -> None:
        return None


class IngestService:
    def __init__(
        self,
        *,
        repo: IngestRepository,
        parser: Parser,
        embeddings: Embeddings | None,
        chunk_size_words: int = 200,
        embedding_batch_size: int = 64,
        parse_worker_factory: Callable[[], ParseWorker] | None = None,
    ) -> None:
        self.repo = repo
        self.parser = parser
        self.embeddings = embeddings
        self.chunk_size_words = chunk_size_words
        self.embedding_batch_size = embedding_batch_size
        self.parse_worker_factory = parse_worker_factory

    def ingest_paths(
        self,
        paths: list[str],
        force_all: bool,
        recursive: bool = False,
        *,
        start_offset: int = 0,
        max_files: int | None = None,
        parse_worker_recycle_every: int = 25,
    ) -> int:
        if start_offset < 0:
            raise ValueError("start_offset must be >= 0")
        if max_files is not None and max_files < 0:
            raise ValueError("max_files must be >= 0")
        if parse_worker_recycle_every <= 0:
            raise ValueError("parse_worker_recycle_every must be >= 1")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be >= 1")

        files = self._discover_files(paths, recursive=recursive)
        files = files[start_offset:]
        if max_files is not None:
            files = files[:max_files]
        if not files:
            return 0

        worker = self._create_parse_worker()
        inserted = 0
        parsed_since_recycle = 0
        try:
            for index, file_path in enumerate(files):
                try:
                    parsed = worker.parse(file_path)
                except Exception as exc:
                    raise RuntimeError(f"Failed to parse {file_path}: {exc}") from exc
                parsed_since_recycle += 1
                if not force_all and self.repo.has_paper(parsed):
                    if index < len(files) - 1 and parsed_since_recycle >= parse_worker_recycle_every:
                        worker.close()
                        worker = self._create_parse_worker()
                        parsed_since_recycle = 0
                    continue
                chunks = chunk_words(parsed.full_text, self.chunk_size_words)
                vectors: list[list[float]] = []
                if self.embeddings is not None:
                    for start in range(0, len(chunks), self.embedding_batch_size):
                        batch = chunks[start : start + self.embedding_batch_size]
                        batch_vectors = self.embeddings.embed(batch)
                        if len(batch) != len(batch_vectors):
                            raise ValueError("Embedding count must match chunk count")
                        vectors.extend(batch_vectors)
                paper_id = self.repo.upsert_paper(parsed, force=force_all)
                self.repo.replace_chunks(paper_id, chunks, vectors)
                inserted += 1
                if index < len(files) - 1 and parsed_since_recycle >= parse_worker_recycle_every:
                    worker.close()
                    worker = self._create_parse_worker()
                    parsed_since_recycle = 0
        finally:
            worker.close()
        return inserted

    def _create_parse_worker(self) -> ParseWorker:
        if self.parse_worker_factory is not None:
            return self.parse_worker_factory()
        return _InlineParseWorker(self.parser)

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
