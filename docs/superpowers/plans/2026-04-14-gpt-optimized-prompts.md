# GPT-Optimized Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all `OpenAISummaryAdapter` prompts in `paperbrain/adapters/llm.py` with detailed role/rubric/schema instructions while preserving existing output contracts.

**Architecture:** Keep the same adapter methods and validators, but replace prompt strings with structured multi-block prompts (role, evidence boundary, rubric, strict JSON schema, default/failure rules). Use a senior reviewer persona for paper summary and senior professor personas for person/topic generation. Add prompt-content regression tests so wording requirements remain enforced.

**Tech Stack:** Python 3.12, pytest, `paperbrain/adapters/llm.py`, `tests/test_openai_adapter.py`

---

## File structure map

- **Modify:** `paperbrain/adapters/llm.py:548-980`
  - Rewrite prompt bodies for metadata, paper summary, corresponding-author fallback, person generation, and topic generation.
- **Modify:** `tests/test_openai_adapter.py:76-860`
  - Add assertions for required persona/rubric/schema phrases in prompt payloads.

### Task 1: Add failing prompt-content tests (red phase)

**Files:**
- Modify: `tests/test_openai_adapter.py:76-860`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Write failing tests for required prompt language**

```python
def test_paper_summary_prompt_includes_top_tier_reviewer_role_and_rubric() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    adapter.summarize_paper(
        "paper text",
        {"slug": "papers/test-paper", "title": "Test Paper", "corresponding_authors": ["alice@example.org"]},
    )
    summary_prompt = next(call["text"] for call in client.summary_calls if call["text"].startswith("Create"))
    assert "senior reviewer for a top-tier scientific journal" in summary_prompt
    assert "innovation, impact, and logical rigor" in summary_prompt
    assert "method-to-result coherence" in summary_prompt
    assert "strict JSON" in summary_prompt


def test_person_generation_prompt_includes_senior_professor_role_and_rubric() -> None:
    class PersonPromptClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return '{"focus_area": [], "big_questions": [{"question": "Q", "why_important": "W", "related_papers": ["papers/test-paper"]}]}'
            return "{}"

    client = PersonPromptClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    adapter.derive_person_cards(
        [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["alice@example.org"]}]
    )
    prompt = next(call["text"] for call in client.summary_calls if call["text"].startswith("Generate person card JSON"))
    assert "senior professor" in prompt
    assert "long-horizon" in prompt
    assert "no fabricated papers" in prompt


def test_topic_generation_prompt_includes_senior_professor_role_and_grouping_rubric() -> None:
    class TopicPromptClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return '[{"slug":"topics/x","type":"topic","topic":"x","related_big_questions":[{"question":"Q","why_important":"W","related_people":["people/a"],"related_papers":["papers/a"]}],"related_people":["people/a"],"related_papers":["papers/a"]}]'
            return "{}"

    client = TopicPromptClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    adapter.derive_topic_cards(
        [{"slug": "people/a", "type": "person", "focus_area": [], "big_questions": [{"question": "Q", "why_important": "W", "related_papers": ["papers/a"]}], "related_papers": ["papers/a"]}]
    )
    prompt = next(call["text"] for call in client.summary_calls if call["text"].startswith("Generate topic card JSON"))
    assert "senior professor" in prompt
    assert "maximize conceptual coherence" in prompt
    assert "strict JSON array only" in prompt
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `python3 -m pytest tests/test_openai_adapter.py -k "reviewer_role_and_rubric or senior_professor_role" -v`  
Expected: FAIL because current prompt wording is not yet upgraded.

- [ ] **Step 3: Commit red-phase tests**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: add failing GPT prompt-content coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement detailed GPT-optimized prompt rewrites

**Files:**
- Modify: `paperbrain/adapters/llm.py:548-980`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Rewrite metadata + paper summary prompts with structured blocks**

```python
prompt = (
    "Role: You are a precise scientific metadata extraction assistant.\n"
    "Objective: Extract bibliographic metadata from first-page OCR text only.\n"
    "Evidence boundary: Use only the text provided below.\n"
    "Checklist:\n"
    "- Authors must be actual author names from the page.\n"
    "- Journal must be the publication venue.\n"
    "- Year must be publication year as integer.\n"
    "Output contract: Return strict JSON object with keys authors (array), journal (string), year (integer).\n"
    "Defaults: unknown authors=[], unknown journal=\"\", unknown year=0.\n\n"
    f"Title: {title}\n\n{first_page_text[:5000]}"
)
```

```python
prompt = (
    "Role: You are a senior reviewer for a top-tier scientific journal who focuses on evaluating "
    "the innovation, impact, and logical rigor of scientific papers.\n"
    "Objective: Summarize this paper using only the provided text.\n"
    "Evidence boundary: Do not use outside knowledge.\n"
    "Rubric:\n"
    "- Novelty/innovation quality\n"
    "- Logical flow of claims and experiments\n"
    "- Method-to-result coherence\n"
    "- Figure-grounded evidence quality\n"
    "- Limitation realism and scope\n"
    "Output contract: Return strict JSON only with required article/review keys.\n"
    "If unknown, use empty strings/arrays as appropriate.\n\n"
    f"Title: {title}\n\n{paper_text[:10000]}"
)
```

- [ ] **Step 2: Rewrite corresponding-author, person, and topic prompts with role + rubric**

```python
prompt = (
    "Role: You are an extraction assistant for author contact metadata.\n"
    "Objective: Extract corresponding author email addresses from first-page OCR text.\n"
    "Output contract: Return JSON array only, no prose, only valid email addresses.\n\n"
    f"Title: {title}\n\n{first_page_text}"
)
```

```python
prompt = (
    "Generate person card JSON for the researcher below.\n"
    "Role: You are a senior professor synthesizing long-horizon research agendas.\n"
    "Evidence boundary: Use only linked paper evidence.\n"
    "Rubric:\n"
    "- Questions must be specific and scientific.\n"
    "- Importance must be strategic and evidence-grounded.\n"
    "- No fabricated papers, no unsupported claims.\n"
    "Output contract: strict JSON object with focus_area and big_questions.\n"
    "focus_area must be [] exactly.\n"
    "big_questions entries require question, why_important, related_papers from linked papers only.\n\n"
    f"Person seed:\n{json.dumps(person_seed, ensure_ascii=False)}\n\n"
    "Linked paper evidence:\n"
    + ("\n".join(evidence_lines) if evidence_lines else "- (none)")
)
```

```python
return (
    "Generate topic card JSON from all provided person cards and big questions.\n"
    "Role: You are a senior professor synthesizing coherent research themes.\n"
    "Evidence boundary: Use only provided person cards.\n"
    "Rubric:\n"
    "- Themes must emerge from input big questions.\n"
    "- Grouping should maximize conceptual coherence.\n"
    "- Preserve traceable people/paper links per grouped question.\n"
    "Output contract: strict JSON array only; each topic card must include slug, type, topic, "
    "related_big_questions, related_people, related_papers.\n"
    "Each related_big_questions entry must include question, why_important, related_people, related_papers.\n\n"
    f"Input person cards:\n{json.dumps(prompt_people, ensure_ascii=False)}"
)
```

- [ ] **Step 3: Run adapter tests**

Run: `python3 -m pytest tests/test_openai_adapter.py -v`  
Expected: PASS.

- [ ] **Step 4: Commit implementation**

```bash
git add paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "feat: rewrite llm prompts with detailed GPT-optimized guidance" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Final validation and plan-close commit

**Files:**
- Modify: `tests/test_openai_adapter.py` (only if assertions need minor tuning)
- Test: `tests/test_summarize_service.py`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Run focused integration checks**

Run: `python3 -m pytest tests/test_openai_adapter.py tests/test_summarize_service.py -q`  
Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `python3 -m pytest -q`  
Expected: PASS (allow existing skipped tests).

- [ ] **Step 3: Commit any final test-tuning adjustments (if present)**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: finalize prompt regression assertions" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
