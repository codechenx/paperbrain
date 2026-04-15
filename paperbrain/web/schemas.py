from dataclasses import dataclass
from typing import Literal

CardType = Literal["paper", "person", "topic"]


@dataclass(slots=True)
class CardListQuery:
    card_type: CardType
    query: str = ""
    page: int = 1
    page_size: int = 20


@dataclass(slots=True)
class CardSummary:
    slug: str
    entity_type: CardType
    body: dict
    sort_value: int
