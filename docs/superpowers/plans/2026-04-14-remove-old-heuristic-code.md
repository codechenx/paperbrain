# Remove Old Heuristic Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy heuristic person/topic derivation code and `DeterministicLLMAdapter` so only the LLM-driven path remains in `llm.py`.

**Architecture:** Delete old helper functions and deterministic adapter from `paperbrain/adapters/llm.py`, then align tests to validate only `OpenAISummaryAdapter` behavior. Add a regression guard that legacy symbols are gone, and keep current strict validation/retry behavior unchanged.

**Tech Stack:** Python 3.12, pytest, `paperbrain/adapters/llm.py`, `tests/test_openai_adapter.py`

---

## File structure map

- **Modify:** `paperbrain/adapters/llm.py:49-305, 1106-1155`
  - Remove `_infer_theme_from_text`, `_derive_person_cards`, `_derive_topic_cards`, and `DeterministicLLMAdapter`.
- **Modify:** `tests/test_openai_adapter.py:1-1100`
  - Remove deterministic-adapter import/tests and add explicit absence regression test.

### Task 1: Add failing regression test for legacy symbol removal

**Files:**
- Modify: `tests/test_openai_adapter.py`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
import paperbrain.adapters.llm as llm_module


def test_llm_module_no_longer_exposes_legacy_heuristic_symbols() -> None:
    assert not hasattr(llm_module, "_infer_theme_from_text")
    assert not hasattr(llm_module, "_derive_person_cards")
    assert not hasattr(llm_module, "_derive_topic_cards")
    assert not hasattr(llm_module, "DeterministicLLMAdapter")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_openai_adapter.py -k legacy_heuristic_symbols -v`  
Expected: FAIL because symbols still exist before cleanup.

- [ ] **Step 3: Commit**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: add failing legacy-symbol removal guard" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Remove old heuristic code and deterministic adapter; align tests

**Files:**
- Modify: `paperbrain/adapters/llm.py`
- Modify: `tests/test_openai_adapter.py`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Remove legacy code from `llm.py`**

```python
# Delete these definitions completely:
# - _infer_theme_from_text(...)
# - _derive_person_cards(...)
# - _derive_topic_cards(...)
# - class DeterministicLLMAdapter
#
# Keep OpenAISummaryAdapter unchanged for:
# - derive_person_cards
# - derive_topic_cards
# - strict validators/retry semantics
```

- [ ] **Step 2: Update tests to remove deterministic adapter references**

```python
# before
from paperbrain.adapters.llm import DeterministicLLMAdapter, OpenAISummaryAdapter

# after
from paperbrain.adapters.llm import OpenAISummaryAdapter
import paperbrain.adapters.llm as llm_module
```

```python
# Remove deterministic-adapter-specific test block(s), keep OpenAI adapter tests only.
# Keep the new legacy-symbol absence test from Task 1.
```

- [ ] **Step 3: Run targeted adapter tests**

Run: `python3 -m pytest tests/test_openai_adapter.py -v`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "refactor: remove legacy heuristic derivation code" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Validate no regressions in summarize flow

**Files:**
- Test: `tests/test_summarize_service.py`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Run focused suites**

Run: `python3 -m pytest tests/test_openai_adapter.py tests/test_summarize_service.py -q`  
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `python3 -m pytest -q`  
Expected: PASS (allow existing skipped tests).

- [ ] **Step 3: Commit final tuning only if needed**

```bash
git add tests/test_openai_adapter.py tests/test_summarize_service.py
git commit -m "test: finalize old-code removal regression coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
