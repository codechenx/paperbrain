from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection
else:
    Connection = Any

CREATE_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS vector;",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
    """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    journal TEXT NOT NULL,
    year INTEGER NOT NULL,
    authors TEXT NOT NULL,
    corresponding_authors TEXT NOT NULL,
    source_path TEXT UNIQUE NOT NULL,
    full_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    UNIQUE (paper_id, chunk_index)
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS paper_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES paper_chunks(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS paper_cards (
    slug TEXT PRIMARY KEY,
    paper_id TEXT UNIQUE NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    card_type TEXT NOT NULL,
    body TEXT NOT NULL
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS person_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS topic_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS paper_person_links (
    paper_slug TEXT NOT NULL REFERENCES paper_cards(slug) ON DELETE CASCADE,
    person_slug TEXT NOT NULL REFERENCES person_cards(slug) ON DELETE CASCADE,
    PRIMARY KEY (paper_slug, person_slug)
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS paper_topic_links (
    paper_slug TEXT NOT NULL REFERENCES paper_cards(slug) ON DELETE CASCADE,
    topic_slug TEXT NOT NULL REFERENCES topic_cards(slug) ON DELETE CASCADE,
    PRIMARY KEY (paper_slug, topic_slug)
);
""".strip(),
    """
CREATE TABLE IF NOT EXISTS person_topic_links (
    person_slug TEXT NOT NULL REFERENCES person_cards(slug) ON DELETE CASCADE,
    topic_slug TEXT NOT NULL REFERENCES topic_cards(slug) ON DELETE CASCADE,
    PRIMARY KEY (person_slug, topic_slug)
);
""".strip(),
    "CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks (paper_id);",
    "CREATE INDEX IF NOT EXISTS idx_paper_cards_card_type_slug ON paper_cards (card_type, slug);",
    "CREATE INDEX IF NOT EXISTS idx_paper_cards_body_trgm ON paper_cards USING gin (body gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_person_cards_body_trgm ON person_cards USING gin (body gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_topic_cards_body_trgm ON topic_cards USING gin (body gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS idx_paper_person_links_person_slug ON paper_person_links (person_slug);",
    "CREATE INDEX IF NOT EXISTS idx_paper_topic_links_topic_slug ON paper_topic_links (topic_slug);",
    "CREATE INDEX IF NOT EXISTS idx_person_topic_links_topic_slug ON person_topic_links (topic_slug);",
]

DROP_STATEMENTS = [
    "DROP TABLE IF EXISTS person_topic_links CASCADE;",
    "DROP TABLE IF EXISTS paper_topic_links CASCADE;",
    "DROP TABLE IF EXISTS paper_person_links CASCADE;",
    "DROP TABLE IF EXISTS paper_embeddings CASCADE;",
    "DROP TABLE IF EXISTS paper_chunks CASCADE;",
    "DROP TABLE IF EXISTS topic_cards CASCADE;",
    "DROP TABLE IF EXISTS person_cards CASCADE;",
    "DROP TABLE IF EXISTS paper_cards CASCADE;",
    "DROP TABLE IF EXISTS papers CASCADE;",
]

SCHEMA_SQL = "\n\n".join(CREATE_STATEMENTS)


@contextmanager
def connect(database_url: str, *, autocommit: bool = False) -> Iterator[Connection]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for database connections") from exc

    with psycopg.connect(database_url, autocommit=autocommit) as connection:
        yield connection


def schema_statements(force: bool) -> list[str]:
    if force:
        return [*DROP_STATEMENTS, *CREATE_STATEMENTS]
    return list(CREATE_STATEMENTS)
