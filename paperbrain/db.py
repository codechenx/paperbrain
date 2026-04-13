SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    journal TEXT NOT NULL,
    year INTEGER NOT NULL,
    authors TEXT NOT NULL,
    corresponding_authors TEXT NOT NULL,
    source_path TEXT UNIQUE NOT NULL,
    full_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES paper_chunks(id) ON DELETE CASCADE,
    embedding vector(8) NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_cards (
    slug TEXT PRIMARY KEY,
    card_type TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_cards (
    slug TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
""".strip()


def schema_statements(force: bool) -> list[str]:
    drops = [
        "DROP TABLE IF EXISTS topic_cards CASCADE;",
        "DROP TABLE IF EXISTS person_cards CASCADE;",
        "DROP TABLE IF EXISTS paper_cards CASCADE;",
        "DROP TABLE IF EXISTS paper_embeddings CASCADE;",
        "DROP TABLE IF EXISTS paper_chunks CASCADE;",
        "DROP TABLE IF EXISTS papers CASCADE;",
    ]
    statements = [x.strip() for x in SCHEMA_SQL.split(";") if x.strip()]
    if force:
        return drops + [f"{x};" for x in statements]
    return [f"{x};" for x in statements]

