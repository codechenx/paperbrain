# Stats Card Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `paperbrain stats` to report `papers`, `paper_cards`, `person_cards`, and `topic_cards`, while removing `authors` and `topics` from the output contract.

**Architecture:** Keep stats aggregation centralized in `paperbrain/services/stats.py` by extending `CorpusStats`, the repository protocol, and database repository methods. Keep CLI wiring in `paperbrain/cli.py` unchanged except for output formatting so command flags and invocation stay stable. Update tests first to lock the new contract before implementation.

**Tech Stack:** Python 3.12, Typer CLI, psycopg/PostgreSQL, pytest.

---

## File Structure Map

- **Modify:** `tests/test_stats_service.py`  
  Convert tests from `authors/topics` expectations to card-count expectations and add SQL assertion coverage for the three card tables.
- **Modify:** `paperbrain/services/stats.py`  
  Replace author/topic counting path with `paper_cards/person_cards/topic_cards` counting in protocol, service, and repository implementation.
- **Modify:** `paperbrain/cli.py`  
  Update `stats` command output string to the new field set.

### Task 1: Lock the new stats contract with failing tests

**Files:**
- Modify: `tests/test_stats_service.py`

- [ ] **Step 1: Write the failing service and CLI contract tests**

```python
class FakeStatsRepo:
    def count_papers(self) -> int:
        return 2

    def count_paper_cards(self) -> int:
        return 3

    def count_person_cards(self) -> int:
        return 4

    def count_topic_cards(self) -> int:
        return 5


def test_stats_service_collect_returns_counts() -> None:
    stats = StatsService(repo=FakeStatsRepo()).collect()
    assert stats == CorpusStats(
        papers=2,
        paper_cards=3,
        person_cards=4,
        topic_cards=5,
    )
```

```python
def test_cli_stats_invokes_run_stats(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_run_stats(database_url: str) -> CorpusStats:
        captured["database_url"] = database_url
        return CorpusStats(papers=5, paper_cards=7, person_cards=11, topic_cards=13)

    class FakeConfig:
        database_url = "postgresql://localhost:5432/paperbrain"

    class FakeStore:
        def __init__(self, path: Any) -> None:
            captured["config_path"] = path

        def load(self) -> FakeConfig:
            return FakeConfig()

    monkeypatch.setattr("paperbrain.cli.ConfigStore", FakeStore)
    monkeypatch.setattr("paperbrain.cli.run_stats", fake_run_stats, raising=False)

    result = CliRunner().invoke(app, ["stats"])

    assert result.exit_code == 0
    assert "papers=5" in result.output
    assert "paper_cards=7" in result.output
    assert "person_cards=11" in result.output
    assert "topic_cards=13" in result.output
    assert "authors=" not in result.output
    assert "topics=" not in result.output
```

- [ ] **Step 2: Add a failing DB stats integration expectation for card count SQL**

```python
def test_run_stats_uses_database_connection(monkeypatch: Any) -> None:
    executed: list[str] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            _ = params
            executed.append(sql)

        def fetchone(self) -> tuple[int]:
            return (1,)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    @contextmanager
    def fake_connect(database_url: str, *, autocommit: bool = False) -> Any:
        assert database_url == "postgresql://localhost:5432/paperbrain"
        assert autocommit is False
        yield FakeConnection()

    monkeypatch.setattr("paperbrain.services.stats.connect", fake_connect)

    stats = run_stats("postgresql://localhost:5432/paperbrain")

    assert stats == CorpusStats(
        papers=1,
        paper_cards=1,
        person_cards=1,
        topic_cards=1,
    )
    assert "SELECT COUNT(*) FROM paper_cards;" in executed
    assert "SELECT COUNT(*) FROM person_cards;" in executed
    assert "SELECT COUNT(*) FROM topic_cards;" in executed
```

- [ ] **Step 3: Run tests to verify RED state**

Run: `python3 -m pytest -q tests/test_stats_service.py`  
Expected: FAIL with dataclass field mismatch and/or missing repository methods (`count_paper_cards`, `count_person_cards`, `count_topic_cards`) until implementation is updated.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/test_stats_service.py
git commit -m "test: define stats card count output contract" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement stats service and CLI output changes

**Files:**
- Modify: `paperbrain/services/stats.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_stats_service.py`

- [ ] **Step 1: Implement minimal `CorpusStats` and repository/service updates**

```python
@dataclass(slots=True)
class CorpusStats:
    papers: int
    paper_cards: int
    person_cards: int
    topic_cards: int


class StatsRepository(Protocol):
    def count_papers(self) -> int:
        raise NotImplementedError

    def count_paper_cards(self) -> int:
        raise NotImplementedError

    def count_person_cards(self) -> int:
        raise NotImplementedError

    def count_topic_cards(self) -> int:
        raise NotImplementedError


class StatsService:
    def collect(self) -> CorpusStats:
        return CorpusStats(
            papers=self.repo.count_papers(),
            paper_cards=self.repo.count_paper_cards(),
            person_cards=self.repo.count_person_cards(),
            topic_cards=self.repo.count_topic_cards(),
        )
```

```python
class DatabaseStatsRepository:
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
```

- [ ] **Step 2: Update CLI stats output string**

```python
def stats(config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path")) -> None:
    config = ConfigStore(config_path).load()
    corpus = run_stats(config.database_url)
    typer.echo(
        "Corpus stats: "
        f"papers={corpus.papers} "
        f"paper_cards={corpus.paper_cards} "
        f"person_cards={corpus.person_cards} "
        f"topic_cards={corpus.topic_cards}"
    )
```

- [ ] **Step 3: Run tests to verify GREEN state**

Run: `python3 -m pytest -q tests/test_stats_service.py`  
Expected: PASS.

- [ ] **Step 4: Run focused CLI verification**

Run: `python3 -m pytest -q tests/test_stats_service.py -k "cli_stats_invokes_run_stats"`  
Expected: PASS with output assertions for `paper_cards/person_cards/topic_cards` and no `authors/topics`.

- [ ] **Step 5: Commit implementation**

```bash
git add paperbrain/services/stats.py paperbrain/cli.py tests/test_stats_service.py
git commit -m "feat: report card counts in stats command" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Final verification

**Files:**
- Modify: none (verification only)
- Test: `tests/test_stats_service.py`

- [ ] **Step 1: Run broader regression slice**

Run: `python3 -m pytest -q tests/test_setup_command.py tests/test_stats_service.py`  
Expected: PASS.

- [ ] **Step 2: Run full repository tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`  
Expected: PASS with existing skip count only.

- [ ] **Step 3: Commit verification notes only if needed**

```bash
git status --short
```

Expected: clean working tree (no extra commit required).

## Final Validation Commands

```bash
python3 -m pytest -q tests/test_stats_service.py
python3 -m pytest -q tests/test_setup_command.py tests/test_stats_service.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Expected:
- Stats contract tests pass with new output fields.
- No regression in CLI/setup-adjacent tests.
- Full suite passes with existing baseline skips only.
