from collections.abc import Iterator, Sequence
from typing import Any

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
    ) -> None:
        self.executed: list[tuple[str, Sequence[Any] | None]] = []
        self.row = row
        self.rows = rows
        self.transaction_entered = 0
        self.transaction_exited = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.executed, row=self.row, rows=self.rows)

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
