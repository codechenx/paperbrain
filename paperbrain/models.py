from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedPaper:
    title: str
    journal: str
    year: int
    authors: list[str]
    corresponding_authors: list[str]
    full_text: str
    source_path: str


@dataclass(slots=True)
class SummaryStats:
    paper_cards: int
    person_cards: int
    topic_cards: int


@dataclass(slots=True)
class SearchResult:
    paper_slug: str
    keyword_rank: float
    vector_rank: float
    score: float
    cards: list[dict] = field(default_factory=list)

