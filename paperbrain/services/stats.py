import json
from dataclasses import dataclass
from typing import Any, Protocol

from paperbrain.db import connect


@dataclass(slots=True)
class CorpusStats:
    papers: int
    authors: int
    topics: int


class StatsRepository(Protocol):
    def count_papers(self) -> int:
        ...

    def count_authors(self) -> int:
        ...

    def count_topics(self) -> int:
        ...


class StatsService:
    def __init__(self, *, repo: StatsRepository) -> None:
        self.repo = repo

    def collect(self) -> CorpusStats:
        return CorpusStats(
            papers=self.repo.count_papers(),
            authors=self.repo.count_authors(),
            topics=self.repo.count_topics(),
        )


class DatabaseStatsRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def count_papers(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM papers;")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def count_authors(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT authors FROM papers;")
            rows = cursor.fetchall()

        authors: set[str] = set()
        for (raw_authors,) in rows:
            if isinstance(raw_authors, list):
                values = raw_authors
            else:
                try:
                    values = json.loads(str(raw_authors))
                except json.JSONDecodeError:
                    values = []
            if isinstance(values, list):
                authors.update(str(value).strip() for value in values if str(value).strip())

        return len(authors)

    def count_topics(self) -> int:
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
