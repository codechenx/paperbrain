from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from paperbrain.web.repository import WebCardRepository


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


def _card_value(card: Any, field: str) -> Any:
    if isinstance(card, Mapping):
        return card[field]
    return getattr(card, field)


def test_list_cards_filters_by_type_and_query_and_returns_has_more() -> None:
    page = 2
    page_size = 1
    expected_limit = page_size + 1
    expected_offset = (page - 1) * page_size
    connection = FakeConnection(
        rows=[
            ("papers/example", "paper", '{"abstract": "Example abstract"}', 100),
            ("papers/overflow", "paper", '{"abstract": "Overflow abstract"}', 99),
        ]
    )
    repo = WebCardRepository(connection)

    cards, has_more = repo.list_cards(card_type="paper", query="genomics", page=page, page_size=page_size)

    assert has_more is True
    assert len(cards) == 1
    assert _card_value(cards[0], "slug") == "papers/example"
    assert _card_value(cards[0], "entity_type") == "paper"
    assert _card_value(cards[0], "body") == {"abstract": "Example abstract"}
    assert _card_value(cards[0], "sort_value") == 100

    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    normalized_sql = _normalize_sql(sql)
    assert "WHERE" in normalized_sql
    assert "FROM paper_cards" in normalized_sql
    assert "card_type = %s" not in normalized_sql
    assert "ILIKE" in normalized_sql
    assert "LIMIT" in normalized_sql
    assert "OFFSET" in normalized_sql
    assert params is not None
    assert "paper" not in params
    assert params.count("%genomics%") >= 1
    assert params[-2:] == (expected_limit, expected_offset)


def test_list_cards_rejects_invalid_card_type() -> None:
    connection = FakeConnection()
    repo = WebCardRepository(connection)

    with pytest.raises(ValueError, match="card_type must be one of"):
        repo.list_cards(card_type="invalid", query="genomics", page=1, page_size=20)

    assert connection.executed == []


def test_get_card_returns_none_for_missing_slug() -> None:
    connection = FakeConnection(row=None)
    repo = WebCardRepository(connection)

    card = repo.get_card(card_type="paper", slug="papers/missing")

    assert card is None
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    normalized_sql = _normalize_sql(sql)
    assert "FROM paper_cards" in normalized_sql
    assert "WHERE" in normalized_sql
    assert params == ("papers/missing",)
