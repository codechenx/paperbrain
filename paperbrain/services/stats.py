from dataclasses import dataclass
from typing import Protocol


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

