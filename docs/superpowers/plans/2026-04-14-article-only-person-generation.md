# Article-Only Person/Topic Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate person and topic cards using only paper cards where `paper_type == "article"`, while keeping paper-card generation unchanged.

**Architecture:** Keep the change in `SummarizeService.run` as the integration boundary: summarize all papers, then filter paper cards to article-only before calling `derive_person_cards`. Topic generation continues from the resulting person set. Tests enforce strict behavior (missing/invalid `paper_type` excluded).

**Tech Stack:** Python 3.12, pytest, `paperbrain/services/summarize.py`, `tests/test_summarize_service.py`

---

## File structure map

- **Modify:** `paperbrain/services/summarize.py`
  - Add article-only filtering right before person-card derivation.
- **Modify:** `tests/test_summarize_service.py`
  - Add new regression tests for mixed article/review and review-only behavior.
  - Update test LLM stubs so article-path tests explicitly return `paper_type: "article"`.

### Task 1: Add failing summarize-service tests (red phase)

**Files:**
- Modify: `tests/test_summarize_service.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Add mixed-type failing test for person/topic derivation input**

```python
def test_summarize_person_generation_uses_article_cards_only() -> None:
    class MixedTypeLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            paper_type = "review" if "lee-immunity" in metadata["slug"] else "article"
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": paper_type,
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            assert [card["slug"] for card in paper_cards] == ["papers/chen-p53-nature-2024-abc123"]
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]
```

- [ ] **Step 2: Add review-only failing test**

```python
def test_summarize_review_only_papers_produce_no_person_or_topic_cards() -> None:
    class ReviewOnlyLLM(FakeLLM):
        def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
            _ = paper_text
            return {
                "slug": metadata["slug"],
                "type": "article",
                "paper_type": "review",
                "title": metadata["title"],
                "summary": "x",
                "corresponding_authors": metadata["corresponding_authors"],
            }

        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            assert paper_cards == []
            return []

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            assert person_cards == []
            return []
```

- [ ] **Step 3: Run targeted tests to confirm failure**

Run:
```bash
python3 -m pytest tests/test_summarize_service.py -k "article_cards_only or review_only_papers_produce_no_person_or_topic_cards" -v
```

Expected:
- FAIL because current service passes all paper cards to person derivation.

- [ ] **Step 4: Commit red tests**

```bash
git add tests/test_summarize_service.py
git commit -m "test: add failing article-only person generation coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement article-only filtering in summarize service

**Files:**
- Modify: `paperbrain/services/summarize.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Filter article cards before `derive_person_cards`**

```python
article_paper_cards = [
    card
    for card in paper_cards
    if str(card.get("paper_type", "")).strip().lower() == "article"
]
person_cards = self.llm.derive_person_cards(article_paper_cards)
topic_cards = self.llm.derive_topic_cards(person_cards)
```

- [ ] **Step 2: Run targeted tests to verify pass**

Run:
```bash
python3 -m pytest tests/test_summarize_service.py -k "article_cards_only or review_only_papers_produce_no_person_or_topic_cards" -v
```

Expected:
- PASS.

- [ ] **Step 3: Commit service implementation**

```bash
git add paperbrain/services/summarize.py tests/test_summarize_service.py
git commit -m "feat: derive person cards from article paper cards only" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Update summarize-service test doubles for strict `paper_type` behavior

**Files:**
- Modify: `tests/test_summarize_service.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Update existing LLM test stubs to set `paper_type: "article"` where article-path behavior is expected**

```python
return {
    "slug": metadata["slug"],
    "type": "article",
    "paper_type": "article",
    "title": metadata["title"],
    "summary": "x",
    "corresponding_authors": metadata["corresponding_authors"],
}
```

- [ ] **Step 2: Run full summarize-service tests**

Run:
```bash
python3 -m pytest tests/test_summarize_service.py -q
```

Expected:
- PASS.

- [ ] **Step 3: Commit test fixture alignment**

```bash
git add tests/test_summarize_service.py
git commit -m "test: align summarize fixtures with strict paper_type filtering" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Final verification

**Files:**
- Modify: none unless fixes required
- Test: focused + full suite

- [ ] **Step 1: Run focused regression checks**

Run:
```bash
python3 -m pytest tests/test_summarize_service.py tests/test_openai_adapter.py -q
```

Expected:
- PASS.

- [ ] **Step 2: Run full suite**

Run:
```bash
python3 -m pytest -q
```

Expected:
- PASS (allow existing skipped tests).

- [ ] **Step 3: Commit any final test-only adjustment (if needed)**

```bash
git add tests/test_summarize_service.py tests/test_openai_adapter.py
git commit -m "test: finalize article-only person generation regressions" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
