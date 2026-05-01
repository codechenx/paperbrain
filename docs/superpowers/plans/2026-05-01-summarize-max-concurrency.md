# Summarize Max-Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `--limit` truncation behavior with `--max-concurrency` so summarize processes all eligible papers while controlling simultaneous LLM requests.

**Architecture:** Update the CLI and service contract from `limit` to `max_concurrency`, then move paper summarization to bounded parallel execution. Keep staged sequencing behavior intact (papers first; downstream only when paper completion gate allows). Preserve explicit scope behavior for `paper/person/topic`.

**Tech Stack:** Python 3.12, Typer, pytest, concurrent.futures

---

## File structure and responsibilities

- `paperbrain/cli.py`
  - CLI option contract (`--max-concurrency`), validation, passthrough to service.
- `paperbrain/services/summarize.py`
  - Core summarize orchestration and paper-stage bounded concurrency implementation.
- `tests/test_setup_command.py`
  - CLI contract tests (`--max-concurrency` accepted, `--limit` rejected).
- `tests/test_summarize_service.py`
  - Service behavior tests: no truncation, bounded concurrency behavior, staged sequencing regression.

### Task 1: Define CLI contract changes with RED tests

**Files:**
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing test that summarize passes `max_concurrency`**

```python
def test_cli_summarize_passes_max_concurrency(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}

    class FakeSummarizeService:
        def __init__(self, *, repo: Any, llm: Any) -> None:
            _ = repo, llm

        def run(self, *, card_scope: str | None, max_concurrency: int = 1) -> SummaryStats:
            calls["card_scope"] = card_scope
            calls["max_concurrency"] = max_concurrency
            return SummaryStats(paper_cards=1, person_cards=0, topic_cards=0)

    # reuse existing setup monkeypatch scaffolding
    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--max-concurrency", "3", "--config-path", str(tmp_path / "cfg.conf")])
    assert result.exit_code == 0
    assert calls["max_concurrency"] == 3
```

- [ ] **Step 2: Add failing test that `--limit` is rejected**

```python
def test_cli_summarize_rejects_legacy_limit_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--limit", "2"])
    assert result.exit_code != 0
    assert "No such option: --limit" in result.output
```

- [ ] **Step 3: Run targeted tests and confirm RED**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "passes_max_concurrency or rejects_legacy_limit_flag"`
Expected: FAIL (CLI not updated yet).

- [ ] **Step 4: Commit RED tests**

```bash
git add tests/test_setup_command.py
git commit -m "test: define max-concurrency summarize cli contract"
```

### Task 2: Implement CLI option replacement

**Files:**
- Modify: `paperbrain/cli.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Replace `--limit` with `--max-concurrency` in summarize command**

```python
def summarize(
    card_scope: str | None = typer.Option(None, "--card-scope"),
    max_concurrency: int = typer.Option(1, "--max-concurrency", help="Max simultaneous LLM summarize requests."),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
```

- [ ] **Step 2: Add positive integer validation at CLI boundary**

```python
if max_concurrency <= 0:
    raise typer.BadParameter("Must be a positive integer.", param_hint="'--max-concurrency'")
```

- [ ] **Step 3: Pass `max_concurrency` into service run**

```python
stats = summarize_service.run(card_scope=normalized_scope, max_concurrency=max_concurrency)
```

- [ ] **Step 4: Run CLI targeted tests and confirm GREEN**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "passes_max_concurrency or rejects_legacy_limit_flag"`
Expected: PASS.

- [ ] **Step 5: Commit CLI implementation**

```bash
git add paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: replace summarize limit with max-concurrency"
```

### Task 3: Define and implement service-level no-truncation + bounded concurrency

**Files:**
- Modify: `tests/test_summarize_service.py`
- Modify: `paperbrain/services/summarize.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Add failing test that all eligible papers are processed**

```python
def test_summarize_paper_scope_processes_all_eligible_papers() -> None:
    repo = FakeSummaryRepo()
    repo.papers_for_summary = [build_summary_paper(slug=f"p-{i}") for i in range(3)]
    llm = FakeLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(card_scope="paper", max_concurrency=2)

    assert stats.paper_cards == 3
    assert len(repo.upserted_paper_cards) == 3
```

- [ ] **Step 2: Add failing test for max_concurrency validation in service (defense-in-depth)**

```python
def test_summarize_rejects_non_positive_max_concurrency() -> None:
    service = SummarizeService(repo=FakeSummaryRepo(), llm=FakeLLM())
    with pytest.raises(ValueError, match="max_concurrency must be positive"):
        service.run(max_concurrency=0)
```

- [ ] **Step 3: Update service signature and remove truncation logic**

```python
def run(self, card_scope: str | None = None, max_concurrency: int = 1) -> SummaryStats:
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be positive")
```

```python
def _summarize_and_upsert_papers(self, *, force_all: bool, max_concurrency: int) -> list[dict]:
    papers = self.repo.list_papers_for_summary(force_all)
    # no slicing/truncation by limit
```

- [ ] **Step 4: Implement bounded parallel paper summarization**

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
    cards = list(ex.map(lambda p: self.llm.summarize_paper(p.full_text, {...}), papers))
for card in cards:
    self.repo.upsert_paper_card(card)
```

- [ ] **Step 5: Run summarize service tests and confirm GREEN**

Run: `python3 -m pytest -q tests/test_summarize_service.py`
Expected: PASS.

- [ ] **Step 6: Commit service changes**

```bash
git add paperbrain/services/summarize.py tests/test_summarize_service.py
git commit -m "feat: add bounded concurrency for paper summarization"
```

### Task 4: Regression for staged sequencing + CLI contract

**Files:**
- Modify: `tests/test_setup_command.py` (if any remaining expectations)
- Modify: `tests/test_summarize_service.py` (if any sequencing assertions need signature updates)
- Test: `tests/test_setup_command.py`, `tests/test_summarize_service.py`

- [ ] **Step 1: Run focused regression tests**

Run: `python3 -m pytest -q tests/test_summarize_service.py tests/test_setup_command.py`
Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`
Expected: PASS with baseline skip count.

- [ ] **Step 3: Manual smoke check for new CLI option**

Run: `python3 paperbrain/main.py summarize --card-scope paper --max-concurrency 2 --config-path ~/.config/paperbrain/paperbrain.conf`
Expected: command accepts option; no `--limit` usage.

- [ ] **Step 4: Commit final touch-ups (if any)**

```bash
git add -A
git commit -m "chore: finalize summarize max-concurrency migration"
```
