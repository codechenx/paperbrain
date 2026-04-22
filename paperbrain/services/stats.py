from dataclasses import dataclass
from typing import Any, Protocol

from paperbrain.db import connect


@dataclass(slots=True)
class CorpusStats:
    papers: int
    paper_cards: int
    person_cards: int
    topic_cards: int


class StatsRepository(Protocol):
    def count_papers(self) -> int:
        ...

    def count_paper_cards(self) -> int:
        ...

    def count_person_cards(self) -> int:
        ...

    def count_topic_cards(self) -> int:
        ...


class StatsService:
    def __init__(self, *, repo: StatsRepository) -> None:
        self.repo = repo

    def collect(self) -> CorpusStats:
        return CorpusStats(
            papers=self.repo.count_papers(),
            paper_cards=self.repo.count_paper_cards(),
            person_cards=self.repo.count_person_cards(),
            topic_cards=self.repo.count_topic_cards(),
        )


class DatabaseStatsRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def count_papers(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM papers;")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def count_paper_cards(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM paper_cards;")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def count_person_cards(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM person_cards;")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def count_topic_cards(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM topic_cards;")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0


def run_stats(database_url: str) -> CorpusStats:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")

    with connect(database_url, autocommit=False) as connection:
        service = StatsService(repo=DatabaseStatsRepository(connection))
        return service.collect()
