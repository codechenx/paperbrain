# Card Format and Author Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export paper/person/topic cards in clean `Design.md` markdown format (no marker comments), always generate `index.md`, and recover missing `corresponding_authors` using OCR/text extraction with OpenAI fallback.

**Architecture:** Keep export formatting in `paperbrain/exporter.py` and export orchestration in `paperbrain/services/export.py`. Keep author recovery logic in `paperbrain/adapters/llm.py` so summarize flow stays centralized: metadata first, OCR/text pattern extraction second, OpenAI fallback third.

**Tech Stack:** Python 3.12, Typer, psycopg, OpenAI SDK, pytest

---

## Planned file structure

- Modify: `paperbrain/exporter.py` — remove marker comments, enforce `Design.md` section headings, add index rendering helper
- Modify: `paperbrain/services/export.py` — write `index.md` grouped by papers/people/topics
- Modify: `paperbrain/adapters/llm.py` — infer corresponding authors from paper text, then OpenAI fallback
- Modify: `paperbrain/services/summarize.py` — ensure inferred corresponding authors are persisted in paper cards and used for person/topic derivation
- Modify: `tests/test_exporter.py` — card markdown format expectations + marker removal + index rendering
- Modify: `tests/test_stats_service.py` (if needed for index expectations) — keep unchanged unless directly impacted
- Modify: `tests/test_summarize_service.py` — missing corresponding-authors recovery test path
- Create/Modify: `tests/test_live_openai_pipeline.py` (optional assertion extension only if needed)

### Task 1: Clean exported markdown structure for all card types

**Files:**
- Modify: `paperbrain/exporter.py`
- Modify: `tests/test_exporter.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_paper_export_has_design_sections_without_markers() -> None:
    md = render_paper_markdown(
        slug="papers/a",
        title="A",
        authors=["Alice"],
        corresponding_authors=["people/alice"],
        journal="Nature",
        year=2024,
        summary_block=(
            "Key question solved: What was solved?\n"
            "Why this question is important: Why it matters.\n"
            "How the paper solves this question: Approach details.\n"
            "Key findings and flow: Results summary.\n"
            "Limitations of the paper: Limits summary."
        ),
        related_topics=["topics/t1"],
    )
    assert "<!-- paperbrain_paper_summary:start -->" not in md
    assert "<!-- paperbrain_paper_summary:end -->" not in md
    assert "## Key question solved" in md
    assert "## Why this question is important" in md


def test_person_topic_exports_follow_design_sections() -> None:
    person_md = render_person_markdown(
        slug="people/alice",
        name="Alice",
        related_papers=["papers/a"],
        related_topics=["topics/t1"],
    )
    topic_md = render_topic_markdown(
        slug="topics/t1",
        topic="Topic One",
        related_papers=["papers/a"],
        related_people=["people/alice"],
    )
    assert "## Focus area" in person_md
    assert "## Big questions" in person_md
    assert "## Related big questions" in topic_md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_exporter.py::test_paper_export_has_design_sections_without_markers tests/test_exporter.py::test_person_topic_exports_follow_design_sections -v`
Expected: FAIL because current exporter still outputs marker comments and simplified section structure.

- [ ] **Step 3: Write minimal implementation**

```python
def render_paper_markdown(
    *,
    slug: str,
    title: str,
    authors: list[str],
    corresponding_authors: list[str],
    journal: str,
    year: int,
    summary_block: str,
    related_topics: list[str],
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "type: paper\n"
        f"title: {_yaml_quoted(title)}\n"
        f"authors: [{author_line}]\n"
        f"journal: {journal}\n"
        f"year: {year}\n"
        "---\n\n"
        "## Key question solved\n"
        f"{_summary_value(summary_sections, 'Key question solved')}\n\n"
        "## Why this question is important\n"
        f"{_summary_value(summary_sections, 'Why this question is important')}\n\n"
        "## How the paper solves this question\n"
        f"{_summary_value(summary_sections, 'How the paper solves this question')}\n\n"
        "## Key findings and flow\n"
        f"{_summary_value(summary_sections, 'Key findings and flow')}\n\n"
        "## Limitations of the paper\n"
        f"{_summary_value(summary_sections, 'Limitations of the paper')}\n\n"
        f"Corresponding authors: {people_links}\n"
        f"Related topics: {topic_links}\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_exporter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/exporter.py tests/test_exporter.py
git commit -m "feat: export cards in design markdown format without markers"
```

### Task 2: Add export `index.md` grouped by card type

**Files:**
- Modify: `paperbrain/services/export.py`
- Modify: `tests/test_exporter.py`

- [ ] **Step 1: Write the failing test**

```python
def test_export_writes_index_grouped_by_type(tmp_path: Path) -> None:
    svc = ExportService(repo=FakeExportRepo())
    stats = svc.export(output_dir=tmp_path)
    assert stats.total_files >= 1
    index_file = tmp_path / "index.md"
    assert index_file.exists()
    content = index_file.read_text(encoding="utf-8")
    assert "## Papers" in content
    assert "## People" in content
    assert "## Topics" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_exporter.py::test_export_writes_index_grouped_by_type -v`
Expected: FAIL because `index.md` is not generated today.

- [ ] **Step 3: Write minimal implementation**

```python
def _render_index(paper_paths: list[str], person_paths: list[str], topic_paths: list[str]) -> str:
    def _section(title: str, paths: list[str]) -> str:
        if not paths:
            return f"## {title}\n\n- (none)\n"
        lines = "\n".join(f"- [[{Path(p).stem}]]" for p in sorted(paths))
        return f"## {title}\n\n{lines}\n"
    return "# PaperBrain Index\n\n" + _section("Papers", paper_paths) + "\n" + _section("People", person_paths) + "\n" + _section("Topics", topic_paths)


# in ExportService.export()
index_content = _render_index(paper_files, person_files, topic_files)
write_markdown(output_dir / "index.md", index_content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_exporter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/services/export.py tests/test_exporter.py
git commit -m "feat: generate export index markdown"
```

### Task 3: Recover missing corresponding authors (OCR/text first, OpenAI fallback)

**Files:**
- Modify: `paperbrain/adapters/llm.py`
- Modify: `paperbrain/services/summarize.py`
- Modify: `tests/test_summarize_service.py`
- Modify: `tests/test_openai_adapter.py` (if OpenAI fallback helper is unit-tested there)

- [ ] **Step 1: Write the failing tests**

```python
def test_summarize_infers_corresponding_authors_when_missing() -> None:
    repo = FakeRepoWithMissingCorrespondingAuthors()
    llm = FakeLLMWithInference(authors=["Alice <alice@uni.edu>"])
    stats = SummarizeService(repo=repo, llm=llm).run(force_all=True)
    assert stats.person_cards == 1
    assert repo.saved_paper_cards[0]["corresponding_authors"] == ["Alice <alice@uni.edu>"]


def test_summarize_uses_openai_fallback_when_text_pattern_missing() -> None:
    repo = FakeRepoWithMissingCorrespondingAuthors()
    llm = FakeLLMWithInference(authors=[])
    llm.openai_fallback_authors = ["Bob <bob@lab.org>"]
    SummarizeService(repo=repo, llm=llm).run(force_all=True)
    assert repo.saved_paper_cards[0]["corresponding_authors"] == ["Bob <bob@lab.org>"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_summarize_service.py::test_summarize_infers_corresponding_authors_when_missing tests/test_summarize_service.py::test_summarize_uses_openai_fallback_when_text_pattern_missing -v`
Expected: FAIL because summarize path does not currently populate missing corresponding authors.

- [ ] **Step 3: Write minimal implementation**

```python
def _extract_corresponding_from_text(paper_text: str) -> list[str]:
    matches = re.findall(r"(?im)corresponding author[s]?:\\s*(.+)$", paper_text)
    values: list[str] = []
    for match in matches:
        for item in re.split(r"[;,]", match):
            normalized = item.strip()
            if normalized and normalized not in values:
                values.append(normalized)
    return values


class OpenAISummaryAdapter:
    def _infer_corresponding_authors(self, paper_text: str, metadata: dict) -> list[str]:
        inferred = _extract_corresponding_from_text(paper_text)
        if inferred:
            return inferred
        prompt = f"Extract corresponding authors from this paper. Return JSON array of strings.\\n\\nTitle: {metadata.get('title','')}\\n\\n{paper_text[:8000]}"
        response = self.client.summarize(prompt, model=self.model)
        return _parse_json_array(response)

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        corresponding = list(metadata.get("corresponding_authors") or [])
        if not corresponding:
            corresponding = self._infer_corresponding_authors(paper_text, metadata)
        # keep rest of summary behavior
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_summarize_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperbrain/adapters/llm.py paperbrain/services/summarize.py tests/test_summarize_service.py tests/test_openai_adapter.py
git commit -m "feat: infer missing corresponding authors for person/topic derivation"
```

### Task 4: Re-export cards and verify outputs

**Files:**
- Modify: `README.md` (only if command/docs examples need adjustment)
- Runtime output directory: `/home/nous/projects/exported_cards`

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 2: Run live pipeline with user-provided DB/OpenAI configuration**

Run:

```bash
python3 -m paperbrain.main setup --url "$DB_URL" --openai-api-key "$OPENAI_API_KEY" --config-path ./config/paperbrain.conf --test-connections
python3 -m paperbrain.main init --url "$DB_URL" --force
python3 -m paperbrain.main ingest /home/nous/projects/paperbrain/tests/pdf --recursive --force-all --config-path ./config/paperbrain.conf
python3 -m paperbrain.main summarize --force-all --config-path ./config/paperbrain.conf
python3 -m paperbrain.main export --output-dir /home/nous/projects/exported_cards --config-path ./config/paperbrain.conf
```

Expected:
- Paper markdown has `Design.md` sections and no marker comments
- Person/topic cards are generated when corresponding authors are inferred
- `/home/nous/projects/exported_cards/index.md` exists

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document updated card export behavior"
```
