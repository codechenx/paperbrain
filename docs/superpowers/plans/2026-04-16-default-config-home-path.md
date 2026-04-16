# Default Config Home Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the default PaperBrain config file location to `~/.config/paperbrain/paperbrain.conf` while keeping `--config-path` overrides unchanged.

**Architecture:** Update the single canonical default path constant in `paperbrain/cli.py`, then align the test that asserts the default path and the README default-path documentation. This keeps runtime behavior centralized and automatically keeps web defaults in sync because web imports the CLI constant.

**Tech Stack:** Python 3.12, Typer CLI, pytest.

---

## File structure and responsibilities

- `paperbrain/cli.py` (modify): source of truth for `DEFAULT_CONFIG_PATH`.
- `tests/test_setup_command.py` (modify): verifies default `config_path` passed by CLI setup command.
- `README.md` (modify): user-facing default path documentation.

---

### Task 1: Update default path constant and CLI expectation test

**Files:**
- Modify: `paperbrain/cli.py`
- Modify/Test: `tests/test_setup_command.py`

- [ ] **Step 1: Run baseline suite**

Run: `python3 -m pytest -q`  
Expected: PASS baseline before edits.

- [ ] **Step 2: Write the failing test update**

```python
# tests/test_setup_command.py (inside test_cli_setup_accepts_openai_options)
assert calls["config_path"] == Path.home() / ".config" / "paperbrain" / "paperbrain.conf"
```

- [ ] **Step 3: Run targeted test to confirm it fails**

Run: `python3 -m pytest tests/test_setup_command.py::test_cli_setup_accepts_openai_options -q`  
Expected: FAIL because code still uses `Path("./config/paperbrain.conf")`.

- [ ] **Step 4: Implement minimal code change**

```python
# paperbrain/cli.py
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paperbrain" / "paperbrain.conf"
```

- [ ] **Step 5: Re-run targeted test to confirm pass**

Run: `python3 -m pytest tests/test_setup_command.py::test_cli_setup_accepts_openai_options -q`  
Expected: PASS.

- [ ] **Step 6: Commit task changes**

```bash
git add paperbrain/cli.py tests/test_setup_command.py
git commit -m "feat: default config path to user config directory"
```

---

### Task 2: Update README default path text and run regressions

**Files:**
- Modify: `README.md`
- Validate: full test suite

- [ ] **Step 1: Update README default path text**

```markdown
Default config path is:
- `~/.config/paperbrain/paperbrain.conf`
```

- [ ] **Step 2: Run full suite after documentation/code updates**

Run: `python3 -m pytest -q`  
Expected: PASS with no regressions.

- [ ] **Step 3: Commit docs update**

```bash
git add README.md
git commit -m "docs: update default config path"
```

---

## Self-review checklist (completed)

1. **Spec coverage:** plan includes code constant change, test alignment, README update, and baseline/post-change full suite runs.
2. **Placeholder scan:** no incomplete placeholder tasks; each action has concrete code/commands.
3. **Type consistency:** all references use `Path.home() / ".config" / "paperbrain" / "paperbrain.conf"` consistently across code and tests.
