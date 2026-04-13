import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from paperbrain.models import ParsedPaper
from paperbrain.utils import slugify

if TYPE_CHECKING:
    from psycopg import Connection
else:
    Connection = Any


class PostgresRepo:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.connection.transaction():
            yield self.connection

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)

    def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> tuple[Any, ...] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return row

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return list(rows)

    def has_source(self, source_path: str) -> bool:
        row = self.fetchone("SELECT 1 FROM papers WHERE source_path = %s", (source_path,))
        return row is not None

    def upsert_paper(self, paper: ParsedPaper, force: bool) -> str:
        paper_hash = hashlib.sha1(paper.source_path.encode("utf-8")).hexdigest()[:12]
        paper_id = f"paper-{paper_hash}"
        slug = f"{slugify(paper.title) or 'untitled-paper'}-{paper_hash}"
        params = (
            paper_id,
            slug,
            paper.title,
            paper.journal,
            paper.year,
            json.dumps(paper.authors),
            json.dumps(paper.corresponding_authors),
            paper.source_path,
            paper.full_text,
        )
        if force:
            row = self.fetchone(
                """
                INSERT INTO papers (
                    id, slug, title, journal, year, authors, corresponding_authors, source_path, full_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_path) DO UPDATE SET
                    slug = EXCLUDED.slug,
                    title = EXCLUDED.title,
                    journal = EXCLUDED.journal,
                    year = EXCLUDED.year,
                    authors = EXCLUDED.authors,
                    corresponding_authors = EXCLUDED.corresponding_authors,
                    full_text = EXCLUDED.full_text,
                    updated_at = NOW()
                RETURNING id;
                """.strip(),
                params,
            )
        else:
            row = self.fetchone(
                """
                INSERT INTO papers (
                    id, slug, title, journal, year, authors, corresponding_authors, source_path, full_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_path) DO NOTHING
                RETURNING id;
                """.strip(),
                params,
            )
        if row is not None:
            return str(row[0])
        existing = self.fetchone("SELECT id FROM papers WHERE source_path = %s", (paper.source_path,))
        if existing is None:
            raise RuntimeError("Failed to upsert paper")
        return str(existing[0])

    def replace_chunks(self, paper_id: str, chunks: list[str], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length mismatch")
        with self.transaction():
            self.execute(
                """
                DELETE FROM paper_embeddings
                WHERE chunk_id IN (SELECT id FROM paper_chunks WHERE paper_id = %s);
                """.strip(),
                (paper_id,),
            )
            self.execute("DELETE FROM paper_chunks WHERE paper_id = %s;", (paper_id,))
            for chunk_index, (chunk_text, vector) in enumerate(zip(chunks, vectors, strict=True)):
                chunk_id = f"{paper_id}-chunk-{chunk_index}"
                self.execute(
                    """
                    INSERT INTO paper_chunks (id, paper_id, chunk_index, chunk_text)
                    VALUES (%s, %s, %s, %s);
                    """.strip(),
                    (chunk_id, paper_id, chunk_index, chunk_text),
                )
                vector_literal = f"[{', '.join(str(value) for value in vector)}]"
                self.execute(
                    """
                    INSERT INTO paper_embeddings (chunk_id, embedding)
                    VALUES (%s, %s::vector);
                    """.strip(),
                    (chunk_id, vector_literal),
                )
