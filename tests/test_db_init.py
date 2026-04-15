import sys

import pytest

from paperbrain.db import CREATE_STATEMENTS, DROP_STATEMENTS, SCHEMA_SQL, connect, schema_statements


def test_schema_sql_contains_pgvector_extension() -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SCHEMA_SQL
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS papers" in SCHEMA_SQL


def test_schema_sql_contains_card_search_indexes() -> None:
    assert "idx_paper_cards_card_type_slug" in SCHEMA_SQL
    assert "idx_paper_cards_body_trgm" in SCHEMA_SQL
    assert "idx_person_cards_body_trgm" in SCHEMA_SQL
    assert "idx_topic_cards_body_trgm" in SCHEMA_SQL
    assert "idx_paper_cards_slug_trgm" in SCHEMA_SQL
    assert "idx_person_cards_slug_trgm" in SCHEMA_SQL
    assert "idx_topic_cards_slug_trgm" in SCHEMA_SQL


def test_schema_statements_include_link_tables() -> None:
    sql = "\n".join(schema_statements(force=False))
    assert "CREATE TABLE IF NOT EXISTS paper_person_links" in sql
    assert "CREATE TABLE IF NOT EXISTS paper_topic_links" in sql
    assert "CREATE TABLE IF NOT EXISTS person_topic_links" in sql


def test_schema_statements_force_includes_drop_before_create() -> None:
    statements = schema_statements(force=True)

    assert statements[: len(DROP_STATEMENTS)] == DROP_STATEMENTS
    assert statements[len(DROP_STATEMENTS) :] == CREATE_STATEMENTS


def test_connect_raises_runtime_error_when_psycopg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "psycopg", None)

    with pytest.raises(RuntimeError, match="psycopg is required for database connections"):
        with connect("postgresql://localhost:5432/paperbrain"):
            pass
