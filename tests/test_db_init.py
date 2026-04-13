from paperbrain.db import SCHEMA_SQL


def test_schema_sql_contains_pgvector_extension() -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS papers" in SCHEMA_SQL

