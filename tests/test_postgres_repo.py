import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from paperbrain.models import ParsedPaper
from paperbrain.repositories.postgres import PostgresRepo


class FakeCursor:
    def __init__(
        self,
        executed: list[tuple[str, Sequence[Any] | None]],
        *,
        row: tuple[Any, ...] | None = None,
        rows: Sequence[tuple[Any, ...]] = (),
    ) -> None:
        self._executed = executed
        self._row = row
        self._rows = rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self._executed.append((sql, params))

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def fetchall(self) -> Sequence[tuple[Any, ...]]:
        return self._rows


class FakeTransaction:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> None:
        self.connection.transaction_entered += 1

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.connection.transaction_exited += 1


class FakeConnection:
    def __init__(
        self,
        *,
        row: tuple[Any, ...] | None = None,
        rows: Sequence[tuple[Any, ...]] = (),
        row_sequence: Sequence[tuple[Any, ...] | None] | None = None,
    ) -> None:
        self.executed: list[tuple[str, Sequence[Any] | None]] = []
        self.row = row
        self.rows = rows
        self.row_sequence = list(row_sequence) if row_sequence is not None else None
        self.transaction_entered = 0
        self.transaction_exited = 0

    def cursor(self) -> FakeCursor:
        row = self.row
        if self.row_sequence is not None and self.row_sequence:
            row = self.row_sequence.pop(0)
        return FakeCursor(self.executed, row=row, rows=self.rows)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


def test_execute_runs_sql_with_params() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.execute("UPDATE papers SET title = %s WHERE id = %s", ("Updated", "paper-1"))

    assert connection.executed == [("UPDATE papers SET title = %s WHERE id = %s", ("Updated", "paper-1"))]


def test_fetchone_returns_row() -> None:
    connection = FakeConnection(row=("paper-1", "Cell"))
    repo = PostgresRepo(connection)

    row = repo.fetchone("SELECT id, journal FROM papers WHERE id = %s", ("paper-1",))

    assert row == ("paper-1", "Cell")
    assert connection.executed == [("SELECT id, journal FROM papers WHERE id = %s", ("paper-1",))]


def test_fetchall_returns_rows_as_list() -> None:
    connection = FakeConnection(rows=(("paper-1",), ("paper-2",)))
    repo = PostgresRepo(connection)

    rows = repo.fetchall("SELECT id FROM papers", None)

    assert rows == [("paper-1",), ("paper-2",)]
    assert connection.executed == [("SELECT id FROM papers", None)]


def test_transaction_yields_connection_inside_context() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    with repo.transaction() as tx_connection:
        assert tx_connection is connection
        assert connection.transaction_entered == 1
        assert connection.transaction_exited == 0

    assert connection.transaction_exited == 1


def _make_parsed_paper() -> ParsedPaper:
    return ParsedPaper(
        title="A Study on Testing",
        journal="Journal of Tests",
        year=2024,
        authors=["Alice", "Bob"],
        corresponding_authors=["Alice"],
        full_text="Full paper text.",
        source_path="/papers/testing.pdf",
    )


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _expected_generated_id_and_slug() -> tuple[str, str]:
    paper_hash = "43aa915ed471"
    return (f"paper-{paper_hash}", f"a-study-on-testing-{paper_hash}")


def test_has_source_returns_true_when_row_exists() -> None:
    connection = FakeConnection(row=(1,))
    repo = PostgresRepo(connection)

    assert repo.has_source("/papers/testing.pdf") is True
    assert connection.executed == [("SELECT 1 FROM papers WHERE source_path = %s", ("/papers/testing.pdf",))]


def test_has_source_returns_false_when_row_missing() -> None:
    connection = FakeConnection(row=None)
    repo = PostgresRepo(connection)

    assert repo.has_source("/papers/missing.pdf") is False
    assert connection.executed == [("SELECT 1 FROM papers WHERE source_path = %s", ("/papers/missing.pdf",))]


def test_upsert_paper_force_false_inserts_and_returns_new_id() -> None:
    connection = FakeConnection(row=("paper-new",))
    repo = PostgresRepo(connection)

    paper_id = repo.upsert_paper(_make_parsed_paper(), force=False)

    assert paper_id == "paper-new"
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    assert "ON CONFLICT (source_path) DO NOTHING" in _normalize_sql(sql)
    assert params is not None
    expected_id, expected_slug = _expected_generated_id_and_slug()
    assert params[0] == expected_id
    assert params[1] == expected_slug
    assert params[7] == "/papers/testing.pdf"
    assert params[5] == json.dumps(["Alice", "Bob"])
    assert params[6] == json.dumps(["Alice"])


def test_upsert_paper_force_false_falls_back_to_existing_id_on_conflict() -> None:
    connection = FakeConnection(row_sequence=[None, ("paper-existing",)])
    repo = PostgresRepo(connection)

    paper_id = repo.upsert_paper(_make_parsed_paper(), force=False)

    assert paper_id == "paper-existing"
    assert len(connection.executed) == 2
    insert_sql, insert_params = connection.executed[0]
    select_sql, select_params = connection.executed[1]
    assert "ON CONFLICT (source_path) DO NOTHING" in _normalize_sql(insert_sql)
    assert insert_params is not None
    expected_id, expected_slug = _expected_generated_id_and_slug()
    assert insert_params[0] == expected_id
    assert insert_params[1] == expected_slug
    assert insert_params[7] == "/papers/testing.pdf"
    assert select_sql == "SELECT id FROM papers WHERE source_path = %s"
    assert select_params == ("/papers/testing.pdf",)


def test_upsert_paper_force_false_raises_when_insert_and_fallback_missing() -> None:
    connection = FakeConnection(row_sequence=[None, None])
    repo = PostgresRepo(connection)

    with pytest.raises(RuntimeError, match=r"^Failed to upsert paper$"):
        repo.upsert_paper(_make_parsed_paper(), force=False)

    assert len(connection.executed) == 2
    insert_sql, insert_params = connection.executed[0]
    select_sql, select_params = connection.executed[1]
    assert "ON CONFLICT (source_path) DO NOTHING" in _normalize_sql(insert_sql)
    assert insert_params is not None
    expected_id, expected_slug = _expected_generated_id_and_slug()
    assert insert_params[0] == expected_id
    assert insert_params[1] == expected_slug
    assert select_sql == "SELECT id FROM papers WHERE source_path = %s"
    assert select_params == ("/papers/testing.pdf",)


def test_upsert_paper_force_true_uses_update_on_conflict() -> None:
    connection = FakeConnection(row=("paper-updated",))
    repo = PostgresRepo(connection)

    paper_id = repo.upsert_paper(_make_parsed_paper(), force=True)

    assert paper_id == "paper-updated"
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    normalized_sql = _normalize_sql(sql)
    assert "ON CONFLICT (source_path) DO UPDATE SET" in normalized_sql
    assert "updated_at = NOW()" in normalized_sql
    assert params is not None
    expected_id, expected_slug = _expected_generated_id_and_slug()
    assert params[0] == expected_id
    assert params[1] == expected_slug
    assert params[7] == "/papers/testing.pdf"
    assert params[8] == "Full paper text."


def test_replace_chunks_deletes_then_reinserts_in_order() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.replace_chunks(
        "paper-123",
        chunks=["first chunk", "second chunk"],
        vectors=[[0.1, 0.2], [1.5, 2.75]],
    )

    assert connection.transaction_entered == 1
    assert connection.transaction_exited == 1
    assert len(connection.executed) == 6
    assert "DELETE FROM paper_embeddings" in connection.executed[0][0]
    assert connection.executed[0][1] == ("paper-123",)
    assert connection.executed[1] == ("DELETE FROM paper_chunks WHERE paper_id = %s;", ("paper-123",))
    assert "INSERT INTO paper_chunks" in connection.executed[2][0]
    assert connection.executed[2][1] == ("paper-123-chunk-0", "paper-123", 0, "first chunk")
    assert "INSERT INTO paper_embeddings" in connection.executed[3][0]
    assert connection.executed[3][1] == ("paper-123-chunk-0", "[0.1, 0.2]")
    assert "INSERT INTO paper_chunks" in connection.executed[4][0]
    assert connection.executed[4][1] == ("paper-123-chunk-1", "paper-123", 1, "second chunk")
    assert "INSERT INTO paper_embeddings" in connection.executed[5][0]
    assert connection.executed[5][1] == ("paper-123-chunk-1", "[1.5, 2.75]")


def test_replace_chunks_raises_on_length_mismatch_without_sql() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    with pytest.raises(ValueError, match="chunks and vectors length mismatch"):
        repo.replace_chunks("paper-123", chunks=["one"], vectors=[[0.1], [0.2]])

    assert connection.executed == []
    assert connection.transaction_entered == 0
    assert connection.transaction_exited == 0


def test_upsert_person_cards_does_not_rebuild_links_when_relation_fields_absent() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.upsert_person_cards(
        [
            {
                "slug": "people/alice-university-org",
                "type": "person",
                "focus_area": "Cancer genomics",
            }
        ]
    )

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "INSERT INTO person_cards" in executed_sql
    assert "DELETE FROM paper_person_links" not in executed_sql
    assert "INSERT INTO paper_person_links" not in executed_sql


def test_upsert_person_cards_rebuilds_links_when_relation_fields_explicitly_present() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.upsert_person_cards(
        [
            {
                "slug": "people/alice-university-org",
                "type": "person",
                "related_papers": [],
            }
        ]
    )

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "DELETE FROM paper_person_links" in executed_sql


def test_upsert_topic_cards_does_not_rebuild_links_when_relation_fields_absent() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.upsert_topic_cards(
        [
            {
                "slug": "topics/cancer-genetics",
                "type": "topic",
                "topic": "Cancer Genetics",
            }
        ]
    )

    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "INSERT INTO topic_cards" in executed_sql
    assert "DELETE FROM paper_topic_links" not in executed_sql
    assert "DELETE FROM person_topic_links" not in executed_sql
    assert "INSERT INTO paper_topic_links" not in executed_sql
    assert "INSERT INTO person_topic_links" not in executed_sql


def test_upsert_topic_cards_rebuilds_each_relation_type_only_when_explicitly_present() -> None:
    connection = FakeConnection()
    repo = PostgresRepo(connection)

    repo.upsert_topic_cards(
        [
            {
                "slug": "topics/cancer-genetics",
                "type": "topic",
                "related_papers": ["papers/a"],
            }
        ]
    )
    executed_sql = "\n".join(sql for sql, _ in connection.executed)
    assert "DELETE FROM paper_topic_links" in executed_sql
    assert "INSERT INTO paper_topic_links" in executed_sql
    assert "DELETE FROM person_topic_links" not in executed_sql
