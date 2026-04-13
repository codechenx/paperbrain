import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from paperbrain.models import ParsedPaper
from paperbrain.utils import slugify

if TYPE_CHECKING:
    from psycopg import Connection
else:
    Connection = Any


@dataclass(slots=True)
class SummaryPaper:
    id: str
    slug: str
    title: str
    journal: str
    year: int
    authors: list[str]
    corresponding_authors: list[str]
    full_text: str


def _decode_json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
    elif isinstance(value, list):
        parsed = value
    else:
        return []

    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item is not None]


def _decode_card_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"body": value}
        if isinstance(parsed, dict):
            return parsed
    return {"body": str(value)}


def _extract_slug_values(card: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        raw = card.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            candidate_values = [raw]
        elif isinstance(raw, Sequence):
            candidate_values = [str(item) for item in raw]
        else:
            continue
        for slug in candidate_values:
            normalized = slug.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            values.append(normalized)
    return values


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

    def browse(self, keyword: str, card_type: str) -> list[dict]:
        if card_type not in {"paper", "person", "topic", "all"}:
            raise ValueError("card_type must be one of: paper, person, topic, all")

        pattern = f"%{keyword}%"
        if card_type == "paper":
            rows = self.fetchall(
                """
                SELECT slug, 'paper' AS entity_type, body
                FROM paper_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                ORDER BY slug;
                """.strip(),
                (pattern, pattern),
            )
        elif card_type == "person":
            rows = self.fetchall(
                """
                SELECT slug, 'person' AS entity_type, body
                FROM person_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                ORDER BY slug;
                """.strip(),
                (pattern, pattern),
            )
        elif card_type == "topic":
            rows = self.fetchall(
                """
                SELECT slug, 'topic' AS entity_type, body
                FROM topic_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                ORDER BY slug;
                """.strip(),
                (pattern, pattern),
            )
        else:
            rows = self.fetchall(
                """
                SELECT slug, 'paper' AS entity_type, body
                FROM paper_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                UNION ALL
                SELECT slug, 'person' AS entity_type, body
                FROM person_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                UNION ALL
                SELECT slug, 'topic' AS entity_type, body
                FROM topic_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                ORDER BY entity_type, slug;
                """.strip(),
                (pattern, pattern, pattern, pattern, pattern, pattern),
            )

        output: list[dict] = []
        for slug, entity_type, body in rows:
            card = _decode_card_payload(body)
            card.setdefault("slug", str(slug))
            card.setdefault("type", str(entity_type))
            output.append(card)
        return output

    def search_hybrid(self, query: str, query_vector: list[float], top_k: int) -> list[dict]:
        if top_k <= 0 or not query_vector:
            return []
        vector_literal = f"[{', '.join(str(value) for value in query_vector)}]"

        rows = self.fetchall(
            """
            WITH ranked AS (
                SELECT
                    p.slug AS paper_slug,
                    COALESCE(
                        MAX(ts_rank_cd(to_tsvector('english', c.chunk_text), plainto_tsquery('english', %s))),
                        0
                    )::float AS keyword_rank,
                    COALESCE(
                        MAX(COALESCE(1 - (e.embedding <=> %s::vector), 0)),
                        0
                    )::float AS vector_rank
                FROM papers p
                JOIN paper_chunks c ON c.paper_id = p.id
                LEFT JOIN paper_embeddings e ON e.chunk_id = c.id
                GROUP BY p.slug
            )
            SELECT paper_slug, keyword_rank, vector_rank
            FROM ranked
            WHERE keyword_rank > 0 OR vector_rank > 0
            ORDER BY (0.6 * keyword_rank + 0.4 * vector_rank) DESC, paper_slug
            LIMIT %s;
            """.strip(),
            (query, vector_literal, top_k),
        )
        return [
            {
                "paper_slug": str(paper_slug),
                "keyword_rank": float(keyword_rank),
                "vector_rank": float(vector_rank),
            }
            for paper_slug, keyword_rank, vector_rank in rows
        ]

    def fetch_related_cards(self, paper_slugs: list[str]) -> dict[str, list[dict]]:
        if not paper_slugs:
            return {}

        grouped: dict[str, list[dict]] = {slug: [] for slug in paper_slugs}
        rows = self.fetchall(
            """
            SELECT p.slug AS paper_slug, p.slug AS card_slug, 'paper' AS entity_type, p.body
            FROM paper_cards p
            WHERE p.slug = ANY(%s)
            UNION ALL
            SELECT l.paper_slug, c.slug AS card_slug, 'person' AS entity_type, c.body
            FROM paper_person_links l
            JOIN person_cards c ON c.slug = l.person_slug
            WHERE l.paper_slug = ANY(%s)
            UNION ALL
            SELECT l.paper_slug, c.slug AS card_slug, 'topic' AS entity_type, c.body
            FROM paper_topic_links l
            JOIN topic_cards c ON c.slug = l.topic_slug
            WHERE l.paper_slug = ANY(%s)
            ORDER BY paper_slug, entity_type, card_slug;
            """.strip(),
            (paper_slugs, paper_slugs, paper_slugs),
        )

        for paper_slug, card_slug, entity_type, body in rows:
            card = _decode_card_payload(body)
            card.setdefault("slug", str(card_slug))
            card.setdefault("type", str(entity_type))
            grouped.setdefault(str(paper_slug), []).append(card)
        return grouped

    def list_papers_for_summary(self, force_all: bool) -> list[SummaryPaper]:
        if force_all:
            rows = self.fetchall(
                """
                SELECT id, slug, title, journal, year, authors, corresponding_authors, full_text
                FROM papers
                ORDER BY updated_at DESC, slug;
                """.strip()
            )
        else:
            rows = self.fetchall(
                """
                SELECT p.id, p.slug, p.title, p.journal, p.year, p.authors, p.corresponding_authors, p.full_text
                FROM papers p
                LEFT JOIN paper_cards pc ON pc.paper_id = p.id
                WHERE pc.paper_id IS NULL
                ORDER BY p.updated_at DESC, p.slug;
                """.strip()
            )

        output: list[SummaryPaper] = []
        for paper_id, slug, title, journal, year, authors, corresponding_authors, full_text in rows:
            output.append(
                SummaryPaper(
                    id=str(paper_id),
                    slug=str(slug),
                    title=str(title),
                    journal=str(journal),
                    year=int(year),
                    authors=_decode_json_list(authors),
                    corresponding_authors=_decode_json_list(corresponding_authors),
                    full_text=str(full_text),
                )
            )
        return output

    def upsert_paper_card(self, card: dict) -> None:
        slug = str(card.get("slug", "")).strip()
        if not slug:
            raise ValueError("Paper card slug is required")

        card_type = str(card.get("type", "article")).strip() or "article"
        body = json.dumps(card, sort_keys=True)
        row = self.fetchone(
            """
            INSERT INTO paper_cards (slug, paper_id, card_type, body)
            SELECT %s, p.id, %s, %s
            FROM papers p
            WHERE p.slug = %s
            ON CONFLICT (slug) DO UPDATE SET
                paper_id = EXCLUDED.paper_id,
                card_type = EXCLUDED.card_type,
                body = EXCLUDED.body
            RETURNING slug;
            """.strip(),
            (slug, card_type, body, slug),
        )
        if row is None:
            raise ValueError(f"Unknown paper slug: {slug}")

    def upsert_person_cards(self, cards: list[dict]) -> None:
        if not cards:
            return

        with self.transaction():
            for card in cards:
                slug = str(card.get("slug", "")).strip()
                if not slug:
                    raise ValueError("Person card slug is required")
                body = json.dumps(card, sort_keys=True)
                self.execute(
                    """
                    INSERT INTO person_cards (slug, body)
                    VALUES (%s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        body = EXCLUDED.body;
                    """.strip(),
                    (slug, body),
                )
                self.execute("DELETE FROM paper_person_links WHERE person_slug = %s;", (slug,))
                for paper_slug in _extract_slug_values(card, "related_papers", "paper_slugs", "papers"):
                    self.execute(
                        """
                        INSERT INTO paper_person_links (paper_slug, person_slug)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """.strip(),
                        (paper_slug, slug),
                    )

    def upsert_topic_cards(self, cards: list[dict]) -> None:
        if not cards:
            return

        with self.transaction():
            for card in cards:
                slug = str(card.get("slug", "")).strip()
                if not slug:
                    raise ValueError("Topic card slug is required")
                body = json.dumps(card, sort_keys=True)
                self.execute(
                    """
                    INSERT INTO topic_cards (slug, body)
                    VALUES (%s, %s)
                    ON CONFLICT (slug) DO UPDATE SET
                        body = EXCLUDED.body;
                    """.strip(),
                    (slug, body),
                )
                self.execute("DELETE FROM paper_topic_links WHERE topic_slug = %s;", (slug,))
                self.execute("DELETE FROM person_topic_links WHERE topic_slug = %s;", (slug,))
                for paper_slug in _extract_slug_values(card, "related_papers", "paper_slugs", "papers"):
                    self.execute(
                        """
                        INSERT INTO paper_topic_links (paper_slug, topic_slug)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """.strip(),
                        (paper_slug, slug),
                    )
                for person_slug in _extract_slug_values(card, "related_people", "person_slugs", "people"):
                    self.execute(
                        """
                        INSERT INTO person_topic_links (person_slug, topic_slug)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """.strip(),
                        (person_slug, slug),
                    )

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
