from paperbrain.db import SCHEMA_SQL, schema_statements


def test_schema_sql_contains_pgvector_extension() -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS papers" in SCHEMA_SQL


def test_schema_statements_include_link_tables() -> None:
    sql = "\n".join(schema_statements(force=False))
    assert "CREATE TABLE IF NOT EXISTS paper_person_links" in sql
    assert "CREATE TABLE IF NOT EXISTS paper_topic_links" in sql
    assert "CREATE TABLE IF NOT EXISTS person_topic_links" in sql
