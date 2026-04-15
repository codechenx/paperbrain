import json
from typing import TYPE_CHECKING, Any

from paperbrain.web.schemas import CardListQuery, CardSummary

if TYPE_CHECKING:
    from psycopg import Connection
else:
    Connection = Any

_VALID_CARD_TYPES = {"paper", "person", "topic"}
_MAX_QUERY_LENGTH = 500


class WebCardRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list_cards(
        self,
        card_type: str,
        query: str,
        page: int,
        page_size: int,
    ) -> tuple[list[CardSummary], bool]:
        self._validate_card_type(card_type)
        self._validate_page(page)
        self._validate_page_size(page_size)
        normalized_query = query.strip()
        self._validate_query(normalized_query)

        normalized = CardListQuery(card_type=card_type, query=normalized_query, page=page, page_size=page_size)
        pattern = f"%{normalized.query}%"
        limit = normalized.page_size + 1
        offset = (normalized.page - 1) * normalized.page_size

        sql = self._list_sql(normalized.card_type)
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (pattern, pattern, limit, offset))
            rows = cursor.fetchall()

        has_more = len(rows) > normalized.page_size
        rows = rows[: normalized.page_size]
        cards = [self._row_to_summary(row) for row in rows]
        return cards, has_more

    def get_card(self, card_type: str, slug: str) -> dict[str, Any] | None:
        self._validate_card_type(card_type)
        sql = self._get_sql(card_type)
        with self.connection.cursor() as cursor:
            cursor.execute(sql, (slug,))
            row = cursor.fetchone()
        if row is None:
            return None

        row_slug, row_entity_type, body, _sort_value = row
        payload = self._decode_card_payload(body)
        payload.setdefault("slug", str(row_slug))
        payload.setdefault("entity_type", str(row_entity_type))
        return payload

    @staticmethod
    def _validate_card_type(card_type: str) -> None:
        if card_type not in _VALID_CARD_TYPES:
            raise ValueError("card_type must be one of: paper, person, topic")

    @staticmethod
    def _validate_page(page: int) -> None:
        if page < 1:
            raise ValueError("page must be >= 1")

    @staticmethod
    def _validate_page_size(page_size: int) -> None:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")

    @staticmethod
    def _validate_query(query: str) -> None:
        if len(query) > _MAX_QUERY_LENGTH:
            raise ValueError("query must be <= 500 characters")

    @staticmethod
    def _list_sql(card_type: str) -> str:
        if card_type == "paper":
            return """
                SELECT c.slug, 'paper' AS entity_type, c.body, p.updated_at::text AS sort_value
                FROM paper_cards c
                JOIN papers p ON p.id = c.paper_id
                WHERE c.slug ILIKE %s OR c.body ILIKE %s
                ORDER BY p.updated_at DESC, c.slug
                LIMIT %s OFFSET %s;
            """.strip()
        if card_type == "person":
            return """
                SELECT slug, 'person' AS entity_type, body, slug AS sort_value
                FROM person_cards
                WHERE slug ILIKE %s OR body ILIKE %s
                ORDER BY slug
                LIMIT %s OFFSET %s;
            """.strip()
        return """
            SELECT slug, 'topic' AS entity_type, body, slug AS sort_value
            FROM topic_cards
            WHERE slug ILIKE %s OR body ILIKE %s
            ORDER BY slug
            LIMIT %s OFFSET %s;
        """.strip()

    @staticmethod
    def _get_sql(card_type: str) -> str:
        if card_type == "paper":
            return """
                SELECT c.slug, 'paper' AS entity_type, c.body, p.updated_at::text AS sort_value
                FROM paper_cards c
                JOIN papers p ON p.id = c.paper_id
                WHERE c.slug = %s;
            """.strip()
        if card_type == "person":
            return """
                SELECT slug, 'person' AS entity_type, body, slug AS sort_value
                FROM person_cards
                WHERE slug = %s;
            """.strip()
        return """
            SELECT slug, 'topic' AS entity_type, body, slug AS sort_value
            FROM topic_cards
            WHERE slug = %s;
        """.strip()

    @staticmethod
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

    @classmethod
    def _row_to_summary(cls, row: tuple[Any, ...]) -> CardSummary:
        slug, entity_type, body, sort_value = row
        return CardSummary(
            slug=str(slug),
            entity_type=str(entity_type),
            body=cls._decode_card_payload(body),
            sort_value=str(sort_value),
        )
