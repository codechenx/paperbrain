# Summarize Staged Sequencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce staged summarize ordering so person cards run only after all paper cards are generated, and topic cards run only after person cards are generated, reducing repeated LLM usage.

**Architecture:** Keep stage orchestration inside `SummarizeService.run` so CLI behavior stays stable while sequencing logic is centralized. Default flow and `--card-scope all` share the same gate: run paper stage first, check remaining unsummarized papers, and only then run downstream stages. Explicit `person` and `topic` scopes remain direct/manual stage commands.

**Tech Stack:** Python 3.12, Typer CLI, pytest

---

### Task 1: Add staged-gating RED tests in summarize service

**Files:**
- Modify: `tests/test_summarize_service.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Write failing test for default flow gating**

```python
def test_summarize_default_skips_person_topic_when_pending_papers_exist() -> None:
    repo = FakeSummaryRepo()
    repo.paper_cards_existing = [{"slug": "existing", "paper_type": "article"}]
    repo.papers_for_summary = [build_summary_paper(slug="new-1"), build_summary_paper(slug="new-2")]
    llm = FakeLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(limit=1)

    assert stats.paper_cards == 1
    assert stats.person_cards == 0
    assert stats.topic_cards == 0
    assert llm.derive_person_calls == 0
    assert llm.derive_topic_calls == 0
```

- [ ] **Step 2: Write failing test for `--card-scope all` gating**

```python
def test_summarize_all_skips_downstream_when_pending_papers_exist() -> None:
    repo = FakeSummaryRepo()
    repo.papers_for_summary = [build_summary_paper(slug="new-1"), build_summary_paper(slug="new-2")]
    llm = FakeLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(card_scope="all", limit=1)

    assert stats.paper_cards == 1
    assert stats.person_cards == 0
    assert stats.topic_cards == 0
    assert llm.derive_person_calls == 0
    assert llm.derive_topic_calls == 0
```

- [ ] **Step 3: Write failing test for downstream run after paper completion**

```python
def test_summarize_all_runs_person_then_topic_after_papers_complete() -> None:
    repo = FakeSummaryRepo()
    repo.papers_for_summary = []
    repo.paper_cards_existing = [{"slug": "p-1", "paper_type": "article"}]
    llm = FakeLLM()
    service = SummarizeService(repo=repo, llm=llm)

    stats = service.run(card_scope="all")

    assert stats.paper_cards == 0
    assert llm.derive_person_calls == 1
    assert llm.derive_topic_calls == 1
    assert stats.person_cards >= 0
    assert stats.topic_cards >= 0
```

- [ ] **Step 4: Run service tests to verify RED**

Run: `python3 -m pytest -q tests/test_summarize_service.py -k "skips_person_topic_when_pending_papers_exist or skips_downstream_when_pending_papers_exist or runs_person_then_topic_after_papers_complete"`
Expected: FAIL on new assertions (gating not implemented yet).

- [ ] **Step 5: Commit RED tests**

```bash
git add tests/test_summarize_service.py
git commit -m "test: define staged summarize gating contract"
```

### Task 2: Implement staged sequencing in summarize service

**Files:**
- Modify: `paperbrain/services/summarize.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Add helper to detect pending papers after paper stage**

```python
def _has_pending_papers(self) -> bool:
    return bool(self.repo.list_papers_for_summary(False))
```

- [ ] **Step 2: Apply gating to `card_scope == "all"` path**

```python
if normalized_scope == "all":
    paper_cards = self._summarize_and_upsert_papers(force_all=True, limit=limit)
    if self._has_pending_papers():
        return SummaryStats(paper_cards=len(paper_cards), person_cards=0, topic_cards=0)
    person_cards = self.llm.derive_person_cards(self._article_cards(self._fetch_all_paper_cards()))
    topic_cards = self.llm.derive_topic_cards(person_cards)
    ...
```

- [ ] **Step 3: Apply same gating to default incremental path**

```python
paper_cards = self._summarize_and_upsert_papers(force_all=False, limit=limit)
if self._has_pending_papers():
    return SummaryStats(paper_cards=len(paper_cards), person_cards=0, topic_cards=0)
# existing downstream logic (or all-from-current-corpus downstream logic)
```

- [ ] **Step 4: Keep explicit `paper/person/topic` scope behavior unchanged**

```python
# Keep:
# if normalized_scope == "paper": ...
# if normalized_scope == "person": ...
# if normalized_scope == "topic": ...
```

- [ ] **Step 5: Run summarize service tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_summarize_service.py`
Expected: PASS.

- [ ] **Step 6: Commit implementation**

```bash
git add paperbrain/services/summarize.py tests/test_summarize_service.py
git commit -m "feat: gate summarize stages by upstream completion"
```

### Task 3: Align CLI command tests with staged sequencing + default limit

**Files:**
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Ensure summarize CLI tests assert default `limit == 1` passthrough**

```python
assert calls["run_limit"] == 1
```

- [ ] **Step 2: Preserve removed alias expectation**

```python
result = runner.invoke(app, ["summary"])
assert result.exit_code != 0
assert "No such command 'summary'" in result.output
```

- [ ] **Step 3: Run targeted CLI tests**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "summarize_uses_runtime_config_and_reports_counts or summary_alias_is_not_available or summarize_routes_gemini_models_through_gemini_summary_adapter or summarize_routes_ollama_models_through_ollama_summary_adapter"`
Expected: PASS.

- [ ] **Step 4: Commit test updates (if any)**

```bash
git add tests/test_setup_command.py
git commit -m "test: align summarize cli contract with staged sequencing"
```

### Task 4: Regression verification

**Files:**
- Modify: none
- Test: `tests/test_summarize_service.py`, `tests/test_setup_command.py`, full suite

- [ ] **Step 1: Run summarize + setup focused regression**

Run: `python3 -m pytest -q tests/test_summarize_service.py tests/test_setup_command.py`
Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`
Expected: PASS with baseline skip count.

- [ ] **Step 3: Verify runtime behavior manually (single-paper batch)**

Run: `python3 paperbrain/main.py summarize --card-scope all --limit 1 --config-path ~/.config/paperbrain/paperbrain.conf`
Expected: prints paper count and zero person/topic while pending papers remain.

- [ ] **Step 4: Commit final polishing (if needed)**

```bash
git add -A
git commit -m "chore: finalize staged summarize sequencing verification"
```
