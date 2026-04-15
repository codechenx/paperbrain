from collections.abc import Sequence
from typing import Any

import pytest

from paperbrain.web.repository import WebRepository


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

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.executed, row=self.row, rows=self.rows)


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def test_list_cards_filters_by_type_and_keyword() -> None:
    connection = FakeConnection(rows=[("papers/example", "paper", "Example Title")])
    repo = WebRepository(connection)

    rows = repo.list_cards(card_type="paper", keyword="genomics")

    assert rows == [("papers/example", "paper", "Example Title")]
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    normalized_sql = _normalize_sql(sql)
    assert "WHERE" in normalized_sql
    assert "card_type = %s" in normalized_sql
    assert "ILIKE" in normalized_sql
    assert params == ("paper", "%genomics%", "%genomics%")


def test_list_cards_rejects_invalid_card_type() -> None:
    connection = FakeConnection()
    repo = WebRepository(connection)

    with pytest.raises(ValueError, match="invalid card_type"):
        repo.list_cards(card_type="invalid", keyword="genomics")

    assert connection.executed == []


def test_get_card_returns_none_for_missing_slug() -> None:
    connection = FakeConnection(row=None)
    repo = WebRepository(connection)

    row = repo.get_card(card_type="paper", slug="papers/missing")

    assert row is None
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    assert "WHERE" in _normalize_sql(sql)
    assert params == ("paper", "papers/missing")
