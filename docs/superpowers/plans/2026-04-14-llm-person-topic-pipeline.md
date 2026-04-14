# LLM Person/Topic Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace heuristic person/topic content synthesis with a two-pass LLM pipeline that (a) generates person big questions from linked papers, (b) generates topics from all person big questions, (c) derives person focus areas from generated topics, and (d) retries once before raising clear validation errors.

**Architecture:** Keep deterministic identity/link extraction from paper `corresponding_authors`, but move all person/topic research-content generation to strict LLM JSON contracts. Generate person cards first, then topic cards, then derive each person’s `focus_area` from topic links before persistence. Add strict validators and one-retry logic for malformed/incomplete LLM output to fail loudly after retry exhaustion.

**Tech Stack:** Python 3.12, pytest, OpenAI adapter (`OpenAISummaryAdapter`), service orchestration (`SummarizeService`)

---

## File structure map

- **Modify:** `paperbrain/adapters/llm.py:20-385, 802-836`
  - Remove heuristic theme/question synthesis for person/topic cards.
  - Add deterministic person-seed extraction, strict JSON parsing/validation, and one-retry LLM generation for person and topic stages.
- **Modify:** `paperbrain/services/summarize.py:31-62`
  - Keep two-pass flow but derive person `focus_area` from generated topic links before persisting person cards.
- **Modify:** `tests/test_openai_adapter.py:76-419`
  - Replace heuristic-derivation assertions with LLM-contract assertions, retry behavior checks, and explicit failure checks.
- **Modify:** `tests/test_summarize_service.py:164-359`
  - Add/adjust service-level tests for post-topic focus-area linking and no-topic-link error behavior.

### Task 1: Add failing adapter tests for person LLM generation + retry semantics

**Files:**
- Modify: `tests/test_openai_adapter.py:76-419`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest


def test_openai_summary_adapter_generates_person_big_questions_from_linked_papers_via_llm() -> None:
    class PersonLLMClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return json.dumps(
                    {
                        "focus_area": [],
                        "big_questions": [
                            {
                                "question": "How can microbiome stratification improve immunotherapy response?",
                                "why_important": "Enables precision treatment selection.",
                                "related_papers": ["papers/test-paper"],
                            }
                        ],
                    }
                )
            return "{}"

    client = PersonLLMClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    person_cards = adapter.derive_person_cards(
        [
            {
                "slug": "papers/test-paper",
                "title": "Test Paper",
                "summary": "Key question solved: Q",
                "corresponding_authors": ["Alice Example <alice@example.org>"],
            }
        ]
    )

    assert person_cards[0]["slug"] == "people/alice-example-org"
    assert person_cards[0]["big_questions"][0]["question"].startswith("How can microbiome")
    assert person_cards[0]["focus_area"] == []
    assert any(call["text"].startswith("Generate person card JSON") for call in client.summary_calls)


def test_openai_summary_adapter_retries_person_generation_once_then_succeeds() -> None:
    class RetryPersonClient(FakeOpenAIClient):
        def __init__(self) -> None:
            super().__init__()
            self.person_attempts = 0

        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                self.person_attempts += 1
                if self.person_attempts == 1:
                    return "{not-json"
                return json.dumps(
                    {
                        "focus_area": [],
                        "big_questions": [
                            {
                                "question": "How do we robustly validate signatures?",
                                "why_important": "Avoids false biomarker claims.",
                                "related_papers": ["papers/test-paper"],
                            }
                        ],
                    }
                )
            return "{}"

    client = RetryPersonClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    cards = adapter.derive_person_cards(
        [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
    )

    assert cards[0]["big_questions"][0]["question"].startswith("How do we robustly")
    assert client.person_attempts == 2


def test_openai_summary_adapter_raises_after_second_invalid_person_generation_attempt() -> None:
    class AlwaysInvalidPersonClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return '{"focus_area": [], "big_questions": []}'
            return "{}"

    adapter = OpenAISummaryAdapter(client=AlwaysInvalidPersonClient(), model="gpt-4.1-mini")
    with pytest.raises(ValueError, match=r"person generation failed after 2 attempts"):
        adapter.derive_person_cards(
            [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_openai_adapter.py -k "person_generation or retries_person_generation" -v`
Expected: FAIL because current adapter still derives person cards heuristically and has no person-stage retry/validation failure path.

- [ ] **Step 3: Commit failing-test checkpoint**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: add failing person LLM generation contract coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement person seed extraction + strict person generation in OpenAI adapter

**Files:**
- Modify: `paperbrain/adapters/llm.py:20-385, 802-806`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Implement deterministic person seeds and strict one-retry LLM person generation**

```python
def _parse_author_identity(author_value: str) -> tuple[str, str]:
    raw = author_value.strip()
    if not raw:
        return ("", "")
    match = re.match(r"^\s*(.*?)\s*<\s*([^>]+)\s*>\s*$", raw)
    if match:
        name = match.group(1).strip()
        email = normalize_email(match.group(2))
        if email:
            return (name or email.split("@", 1)[0], email)
    email = normalize_email(raw)
    if email:
        return (email.split("@", 1)[0], email)
    return (raw, "")


def _build_person_seeds(paper_cards: list[dict]) -> list[dict]:
    seeds_by_slug: dict[str, dict] = {}
    for paper_card in paper_cards:
        paper_slug = str(paper_card.get("slug", "")).strip()
        for raw_author in paper_card.get("corresponding_authors", []):
            name, email = _parse_author_identity(str(raw_author))
            identity = email or name
            if not identity:
                continue
            person_slug = f"people/{slugify(identity)}"
            seed = seeds_by_slug.setdefault(
                person_slug,
                {
                    "slug": person_slug,
                    "type": "person",
                    "name": name or identity,
                    "email": email,
                    "affiliation": email.split("@", 1)[1] if email and "@" in email else "Unknown affiliation",
                    "related_papers": [],
                },
            )
            if paper_slug and paper_slug not in seed["related_papers"]:
                seed["related_papers"].append(paper_slug)
    return [seeds_by_slug[slug] for slug in sorted(seeds_by_slug)]


def _validate_person_payload(payload: dict, *, allowed_papers: set[str]) -> dict:
    big_questions = payload.get("big_questions")
    if not isinstance(big_questions, list) or not big_questions:
        raise ValueError("big_questions must be a non-empty array")
    validated_questions: list[dict] = []
    for item in big_questions:
        question = str(item.get("question", "")).strip()
        why = str(item.get("why_important", "")).strip()
        related = [str(v).strip() for v in item.get("related_papers", []) if str(v).strip()]
        if not question or not why or not related:
            raise ValueError("each big question must include question, why_important, related_papers")
        if any(slug not in allowed_papers for slug in related):
            raise ValueError("big question contains unknown related paper slug")
        validated_questions.append({"question": question, "why_important": why, "related_papers": related})
    return {"focus_area": [], "big_questions": validated_questions}
```

- [ ] **Step 2: Wire `derive_person_cards` to use prompts + retry-once behavior**

```python
def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
    seeds = _build_person_seeds(paper_cards)
    paper_by_slug = {str(card.get("slug", "")).strip(): card for card in paper_cards}
    output: list[dict] = []
    for seed in seeds:
        allowed = set(seed["related_papers"])
        evidence = [paper_by_slug[slug] for slug in seed["related_papers"] if slug in paper_by_slug]
        prompt = (
            "Generate person card JSON from linked paper cards. "
            "Return strict JSON object with keys: big_questions (array of {question, why_important, related_papers}).\n\n"
            f"Person seed: {json.dumps(seed, ensure_ascii=True)}\n\n"
            f"Linked paper cards: {json.dumps(evidence, ensure_ascii=True)}"
        )
        errors: list[str] = []
        validated: dict | None = None
        for _ in range(2):
            raw = self.client.summarize(prompt, model=self.model)
            parsed = self._extract_json_object(raw)
            try:
                validated = _validate_person_payload(parsed, allowed_papers=allowed)
                break
            except ValueError as exc:
                errors.append(str(exc))
        if validated is None:
            raise ValueError(f"person generation failed after 2 attempts for {seed['slug']}: {errors[-1]}")
        output.append({**seed, "focus_area": validated["focus_area"], "big_questions": validated["big_questions"]})
    return output
```

- [ ] **Step 3: Run tests to verify person generation path passes**

Run: `pytest tests/test_openai_adapter.py -k "person_generation or retries_person_generation" -v`
Expected: PASS for new person-generation tests.

- [ ] **Step 4: Commit**

```bash
git add paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "feat: implement strict LLM person big-question generation with retry" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Add failing tests for topic generation and topic-stage retry/failure behavior

**Files:**
- Modify: `tests/test_openai_adapter.py:304-419`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Replace deterministic-topic tests with LLM-topic contract tests**

```python
def test_openai_summary_adapter_generates_topics_from_all_person_big_questions_via_llm() -> None:
    class TopicLLMClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/gut-microbiome-and-lung-cancer-treatment",
                            "type": "topic",
                            "topic": "gut microbiome and lung cancer treatment",
                            "related_big_questions": [
                                {
                                    "question": "How can gut microbiome signals improve lung cancer treatment response?",
                                    "why_important": "Could personalize treatment and improve outcomes.",
                                    "related_papers": ["papers/a"],
                                    "related_people": ["people/alice-example-org"],
                                }
                            ],
                            "related_people": ["people/alice-example-org"],
                            "related_papers": ["papers/a"],
                        }
                    ]
                )
            return "{}"

    adapter = OpenAISummaryAdapter(client=TopicLLMClient(), model="gpt-4.1-mini")
    topic_cards = adapter.derive_topic_cards(
        [
            {
                "slug": "people/alice-example-org",
                "type": "person",
                "focus_area": [],
                "big_questions": [
                    {
                        "question": "How can gut microbiome signals improve lung cancer treatment response?",
                        "why_important": "Could personalize treatment and improve outcomes.",
                        "related_papers": ["papers/a"],
                    }
                ],
                "related_papers": ["papers/a"],
            }
        ]
    )
    assert topic_cards[0]["slug"] == "topics/gut-microbiome-and-lung-cancer-treatment"
    assert topic_cards[0]["related_people"] == ["people/alice-example-org"]


def test_openai_summary_adapter_retries_topic_generation_once_then_raises() -> None:
    class AlwaysInvalidTopicClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return '[{"slug":"topics/x","type":"topic","topic":"x","related_big_questions":[]}]'
            return "{}"

    adapter = OpenAISummaryAdapter(client=AlwaysInvalidTopicClient(), model="gpt-4.1-mini")
    with pytest.raises(ValueError, match=r"topic generation failed after 2 attempts"):
        adapter.derive_topic_cards(
            [
                {
                    "slug": "people/alice-example-org",
                    "type": "person",
                    "focus_area": [],
                    "big_questions": [
                        {"question": "Q", "why_important": "W", "related_papers": ["papers/a"]}
                    ],
                    "related_papers": ["papers/a"],
                }
            ]
        )
```

- [ ] **Step 2: Run tests to verify they fail first**

Run: `pytest tests/test_openai_adapter.py -k "generates_topics_from_all_person_big_questions or retries_topic_generation" -v`
Expected: FAIL because current topic generation uses heuristic grouping and does not use strict topic prompt+retry validation.

- [ ] **Step 3: Commit failing-test checkpoint**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: add failing LLM topic generation contract coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Implement strict topic generation + remove heuristic topic/theme synthesis

**Files:**
- Modify: `paperbrain/adapters/llm.py:20-385, 805-836`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Remove heuristic topic generation internals and add strict validator**

```python
def _validate_topic_cards(payload: object, *, known_people: set[str], known_papers: set[str]) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("topic payload must be a non-empty JSON array")
    validated: list[dict] = []
    for topic in payload:
        slug = str(topic.get("slug", "")).strip()
        label = str(topic.get("topic", "")).strip()
        related_people = [str(v).strip() for v in topic.get("related_people", []) if str(v).strip()]
        related_papers = [str(v).strip() for v in topic.get("related_papers", []) if str(v).strip()]
        big_questions = topic.get("related_big_questions")
        if not slug or not label or not related_people or not related_papers:
            raise ValueError("topic card missing required fields")
        if any(person not in known_people for person in related_people):
            raise ValueError("topic card references unknown related_people slug")
        if any(paper not in known_papers for paper in related_papers):
            raise ValueError("topic card references unknown related_papers slug")
        if not isinstance(big_questions, list) or not big_questions:
            raise ValueError("related_big_questions must be non-empty")
        validated.append(
            {
                "slug": slug,
                "type": "topic",
                "topic": label,
                "related_big_questions": big_questions,
                "related_people": related_people,
                "related_papers": related_papers,
            }
        )
    return validated
```

- [ ] **Step 2: Implement `derive_topic_cards` as one strict LLM pass with one retry**

```python
def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
    if not person_cards:
        return []
    known_people = {str(card.get("slug", "")).strip() for card in person_cards if str(card.get("slug", "")).strip()}
    known_papers = {
        str(slug).strip()
        for card in person_cards
        for slug in card.get("related_papers", [])
        if str(slug).strip()
    }
    prompt = (
        "Generate topic card JSON from all person-card big questions. "
        "Return strict JSON array of topic cards with keys: slug, type, topic, "
        "related_big_questions[{question,why_important,related_papers,related_people}], "
        "related_people, related_papers.\n\n"
        f"Person cards: {json.dumps(person_cards, ensure_ascii=True)}"
    )
    errors: list[str] = []
    for _ in range(2):
        raw = self.client.summarize(prompt, model=self.model)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        try:
            return _validate_topic_cards(parsed, known_people=known_people, known_papers=known_papers)
        except ValueError as exc:
            errors.append(str(exc))
    raise ValueError(f"topic generation failed after 2 attempts: {errors[-1]}")
```

- [ ] **Step 3: Run topic adapter tests**

Run: `pytest tests/test_openai_adapter.py -k "topic_generation" -v`
Expected: PASS for new topic-generation tests.

- [ ] **Step 4: Commit**

```bash
git add paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "feat: implement strict LLM topic generation with retry and validation" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Add failing service tests for post-topic focus-area linking and error propagation

**Files:**
- Modify: `tests/test_summarize_service.py:164-359`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Add service-level tests**

```python
def test_summarize_populates_person_focus_area_from_generated_topics() -> None:
    repo = FakeRepo()

    class FocusAreaLLM(FakeLLM):
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "name": "Alice",
                    "email": "alice@university.org",
                    "affiliation": "university.org",
                    "focus_area": [],
                    "big_questions": [
                        {"question": "Q1", "why_important": "W1", "related_papers": [paper_cards[0]["slug"]]}
                    ],
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "topics/cancer-immunology",
                    "type": "topic",
                    "topic": "cancer immunology",
                    "related_big_questions": [
                        {
                            "question": "Q1",
                            "why_important": "W1",
                            "related_papers": [person_cards[0]["related_papers"][0]],
                            "related_people": [person_cards[0]["slug"]],
                        }
                    ],
                    "related_people": [person_cards[0]["slug"]],
                    "related_papers": [person_cards[0]["related_papers"][0]],
                }
            ]

    SummarizeService(repo=repo, llm=FocusAreaLLM()).run(force_all=False)
    assert repo.person_cards[0]["focus_area"] == ["cancer immunology"]


def test_summarize_raises_when_person_has_no_linked_topic() -> None:
    repo = FakeRepo()

    class MissingTopicLinkLLM(FakeLLM):
        def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
            return [
                {
                    "slug": "people/alice-university-org",
                    "type": "person",
                    "focus_area": [],
                    "big_questions": [{"question": "Q1", "why_important": "W1", "related_papers": [paper_cards[0]["slug"]]}],
                    "related_papers": [paper_cards[0]["slug"]],
                }
            ]

        def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
            _ = person_cards
            return [
                {
                    "slug": "topics/cancer-immunology",
                    "type": "topic",
                    "topic": "cancer immunology",
                    "related_big_questions": [],
                    "related_people": [],
                    "related_papers": [],
                }
            ]

    with pytest.raises(ValueError, match=r"No linked topics found for person card"):
        SummarizeService(repo=repo, llm=MissingTopicLinkLLM()).run(force_all=False)
```

- [ ] **Step 2: Run service tests to verify they fail first**

Run: `pytest tests/test_summarize_service.py -k "focus_area_from_generated_topics or no_linked_topic" -v`
Expected: FAIL because service currently persists person cards before topic generation and never backfills focus areas from topic links.

- [ ] **Step 3: Commit failing-test checkpoint**

```bash
git add tests/test_summarize_service.py
git commit -m "test: add failing summarize focus-area linking coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 6: Implement summarize-stage focus-area linking, then run verification suite

**Files:**
- Modify: `paperbrain/services/summarize.py:31-62`
- Modify: `tests/test_summarize_service.py:164-359`
- Test: `tests/test_openai_adapter.py`
- Test: `tests/test_summarize_service.py`

- [ ] **Step 1: Implement focus-area linking helper and reorder operations**

```python
def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _apply_focus_areas_from_topics(person_cards: list[dict], topic_cards: list[dict]) -> None:
    topics_by_person: dict[str, list[str]] = {}
    for topic in topic_cards:
        topic_name = str(topic.get("topic", "")).strip()
        if not topic_name:
            continue
        for person_slug in _as_str_list(topic.get("related_people")):
            entries = topics_by_person.setdefault(person_slug, [])
            if topic_name not in entries:
                entries.append(topic_name)

    for person in person_cards:
        slug = str(person.get("slug", "")).strip()
        focus_areas = topics_by_person.get(slug, [])
        if not focus_areas:
            raise ValueError(f"No linked topics found for person card: {slug}")
        person["focus_area"] = focus_areas
```

```python
person_cards = self.llm.derive_person_cards(paper_cards)
topic_cards = self.llm.derive_topic_cards(person_cards)
_apply_focus_areas_from_topics(person_cards, topic_cards)
self.repo.upsert_person_cards(person_cards, replace_existing=force_all)
self.repo.upsert_topic_cards(topic_cards, replace_existing=force_all)
```

- [ ] **Step 2: Run targeted tests**

Run: `pytest tests/test_openai_adapter.py tests/test_summarize_service.py -q`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `pytest -q`
Expected: PASS (existing baseline: all tests green except any intentionally skipped tests).

- [ ] **Step 4: Commit final implementation**

```bash
git add paperbrain/adapters/llm.py paperbrain/services/summarize.py tests/test_openai_adapter.py tests/test_summarize_service.py
git commit -m "feat: move person/topic generation to strict two-pass LLM pipeline" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
