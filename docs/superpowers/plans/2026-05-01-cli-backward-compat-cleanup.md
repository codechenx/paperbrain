# CLI Backward-Compat Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unneeded CLI backward-compat artifacts and keep only canonical CLI contract paths.

**Architecture:** Keep runtime CLI behavior focused on supported commands/options only, with no compatibility shims. Remove legacy-focused guardrail tests per user request, and keep canonical positive-contract tests as the source of truth. Do not change non-CLI logic.

**Tech Stack:** Python 3.12, Typer, pytest

---

### Task 1: Remove backward-compat test artifacts from CLI suite

**Files:**
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Remove legacy/compat rejection tests**

Delete these tests from `tests/test_setup_command.py`:

```python
def test_cli_summary_alias_is_not_available() -> None: ...
def test_cli_summarize_rejects_legacy_force_all_flag() -> None: ...
def test_cli_summarize_rejects_legacy_limit_flag() -> None: ...
```

- [ ] **Step 2: Keep canonical summarize contract tests intact**

Retain and verify canonical tests remain present:

```python
def test_cli_summarize_passes_max_concurrency(...)
def test_cli_summarize_rejects_invalid_card_scope()
def test_cli_summarize_rejects_non_positive_max_concurrency()
```

- [ ] **Step 3: Run targeted CLI tests**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "summarize_passes_max_concurrency or summarize_rejects_invalid_card_scope or summarize_rejects_non_positive_max_concurrency"`
Expected: PASS.

- [ ] **Step 4: Commit Task 1**

```bash
git add tests/test_setup_command.py
git commit -m "test: remove legacy cli compatibility guardrail tests"
```

### Task 2: Audit CLI runtime for backward-compat code and remove any remnants

**Files:**
- Modify: `paperbrain/cli.py` (only if compatibility code exists)
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Add a focused CLI command-surface test**

Add/update a test asserting canonical summarize surface:

```python
def test_cli_summarize_help_shows_canonical_options() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["summarize", "--help"])
    assert result.exit_code == 0
    assert "--card-scope" in result.output
    assert "--max-concurrency" in result.output
    assert "--config-path" in result.output
```

- [ ] **Step 2: Remove runtime compatibility remnants if found**

If any legacy alias/compat command wiring is found in `paperbrain/cli.py`, remove it.

Canonical summarize command should stay in this shape:

```python
@app.command()
def summarize(
    card_scope: str | None = typer.Option(None, "--card-scope"),
    max_concurrency: int = typer.Option(1, "--max-concurrency", ...),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
```

- [ ] **Step 3: Run CLI test slice**

Run: `python3 -m pytest -q tests/test_setup_command.py -k "summarize_help_shows_canonical_options or summarize_passes_max_concurrency"`
Expected: PASS.

- [ ] **Step 4: Commit Task 2**

```bash
git add paperbrain/cli.py tests/test_setup_command.py
git commit -m "test: enforce canonical summarize cli surface"
```

### Task 3: Regression verification

**Files:**
- Modify: none expected
- Test: `tests/test_setup_command.py`, full suite

- [ ] **Step 1: Run setup command test module**

Run: `python3 -m pytest -q tests/test_setup_command.py`
Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit only if additional required fixes were made**

```bash
git add -A
git commit -m "chore: finalize cli backward-compat cleanup"
```
