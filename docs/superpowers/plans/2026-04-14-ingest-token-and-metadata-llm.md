# Ingest Token and Metadata LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce downstream token usage by cleaning Docling markdown (remove image payloads and references section) and make metadata extraction LLM-only from a first-two-pages text window.

**Architecture:** Keep ingest/summarize boundaries intact: ingest cleans and persists `full_text`, summarize performs metadata extraction first via one strict JSON LLM call, then builds paper summary from cleaned full text. Metadata extraction will include title/authors/journal/year/corresponding_authors and will not use heuristic fallback for those fields.

**Tech Stack:** Python 3.12, Docling adapter, OpenAI summary adapter, pytest

---

## File structure map

- **Modify:** `paperbrain/adapters/docling.py:13-215`
  - Add markdown-cleaning helpers and invoke them before storing `full_text`.
- **Modify:** `paperbrain/adapters/llm.py:81-845`
  - Change metadata extraction contract and sequencing to metadata-first (LLM-only) using first-two-pages text window.
- **Modify:** `tests/test_ingest_service.py:99-207`
  - Add/adjust parser tests for image payload stripping and references trimming.
- **Modify:** `tests/test_openai_adapter.py:174-620`
  - Add/adjust tests for metadata prompt scope, metadata-first sequencing, and no heuristic fallback behavior.

### Task 1: Add failing ingest-cleaning tests (red phase)

**Files:**
- Modify: `tests/test_ingest_service.py:99-240`
- Test: `tests/test_ingest_service.py`

- [ ] **Step 1: Add a failing test for image payload stripping while preserving caption text**

```python
def test_docling_parser_removes_image_payload_but_keeps_caption_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeDocument:
        title = "Image Payload Test"
        metadata = {}

        def export_to_markdown(self) -> str:
            return (
                "# Results\n"
                "Figure 1. Tumor volume trend.\n"
                "![figure](data:image/png;base64,AAAAABBBBB)\n"
                '<img alt="x" src="data:image/png;base64,CCCCCDDDDD" />\n'
                "Legend text should remain.\n"
            )

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert "data:image/png;base64" not in parsed.full_text
    assert "![figure]" not in parsed.full_text
    assert "<img" not in parsed.full_text
    assert "Figure 1. Tumor volume trend." in parsed.full_text
    assert "Legend text should remain." in parsed.full_text
```

- [ ] **Step 2: Add a failing test for trimming references-style sections**

```python
@pytest.mark.parametrize("heading", ["## References", "## Bibliography", "## Works Cited"])
def test_docling_parser_trims_references_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heading: str) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeDocument:
        title = "References Trim Test"
        metadata = {}

        def export_to_markdown(self) -> str:
            return (
                "# Discussion\n"
                "Main findings remain.\n\n"
                f"{heading}\n"
                "[1] Should be removed\n"
                "[2] Should also be removed\n"
            )

    class FakeConverter:
        def convert(self, path: str):  # noqa: ANN201
            _ = path
            return types.SimpleNamespace(document=FakeDocument())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parsed = DoclingParser().parse_pdf(pdf_path)

    assert "Main findings remain." in parsed.full_text
    assert "Should be removed" not in parsed.full_text
    assert "References" not in parsed.full_text
    assert "Bibliography" not in parsed.full_text
    assert "Works Cited" not in parsed.full_text
```

- [ ] **Step 3: Run targeted parser tests to confirm failures**

Run: `python3 -m pytest tests/test_ingest_service.py -k "image_payload or trims_references" -v`  
Expected: FAIL because parser cleanup logic is not implemented yet.

- [ ] **Step 4: Commit red-phase tests**

```bash
git add tests/test_ingest_service.py
git commit -m "test: add failing ingest cleanup coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement Docling markdown cleanup

**Files:**
- Modify: `paperbrain/adapters/docling.py:13-215`
- Test: `tests/test_ingest_service.py`

- [ ] **Step 1: Add image payload stripping + references trimming helpers**

```python
class DoclingParser:
    @staticmethod
    def _strip_image_payloads(markdown_content: str) -> str:
        cleaned = re.sub(r"!\[[^\]]*\]\(\s*data:image\/[^)]+\)", "", markdown_content, flags=re.IGNORECASE)
        cleaned = re.sub(r"<img\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"data:image\/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _trim_references_section(markdown_content: str) -> str:
        marker = re.search(
            r"(?im)^\s{0,3}(?:#{1,6}\s*)?(references|bibliography|works cited)\s*$",
            markdown_content,
        )
        if not marker:
            return markdown_content.strip()
        return markdown_content[: marker.start()].rstrip()
```

- [ ] **Step 2: Apply cleanup in `parse_pdf` before returning `ParsedPaper`**

```python
if document is not None and hasattr(document, "export_to_markdown"):
    content = document.export_to_markdown()
elif hasattr(result, "markdown"):
    content = str(result.markdown)
else:
    content = str(result)

cleaned_content = self._strip_image_payloads(content)
cleaned_content = self._trim_references_section(cleaned_content)
first_page_text = self._extract_first_page_text(document, cleaned_content)

return ParsedPaper(
    title=title or path.stem,
    journal=journal or "Unknown Journal",
    year=year or 1970,
    authors=authors,
    corresponding_authors=corresponding_authors,
    full_text=cleaned_content.strip(),
    source_path=str(path),
)
```

- [ ] **Step 3: Run parser tests to verify pass**

Run: `python3 -m pytest tests/test_ingest_service.py -v`  
Expected: PASS.

- [ ] **Step 4: Commit parser cleanup implementation**

```bash
git add paperbrain/adapters/docling.py tests/test_ingest_service.py
git commit -m "feat: clean docling markdown for token-efficient ingest" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Add failing metadata-sequencing tests (red phase)

**Files:**
- Modify: `tests/test_openai_adapter.py:430-700`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Add failing test for metadata-first call and expanded metadata contract**

```python
def test_openai_summary_adapter_extracts_title_and_metadata_first_from_two_page_window() -> None:
    class MetadataFirstClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract bibliographic metadata from the first-two-pages OCR/text"):
                return json.dumps(
                    {
                        "title": "LLM Extracted Title",
                        "authors": ["A", "B"],
                        "journal": "Nature",
                        "year": 2025,
                        "corresponding_authors": ["author@example.org"],
                    }
                )
            return "generated summary"

    client = MetadataFirstClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper_text = "page-1\n" + ("x" * 9000) + "\nTAIL-MARKER-SHOULD-NOT-BE-IN-METADATA-PROMPT"

    card = adapter.summarize_paper(paper_text, {"slug": "papers/test-paper", "title": "Original Title"})

    assert card["title"] == "LLM Extracted Title"
    assert card["authors"] == ["A", "B"]
    assert card["journal"] == "Nature"
    assert card["year"] == 2025
    assert card["corresponding_authors"] == ["author@example.org"]
    assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-two-pages OCR/text")
    assert "title (string)" in client.summary_calls[0]["text"]
    assert "corresponding_authors (array of strings)" in client.summary_calls[0]["text"]
    assert "TAIL-MARKER-SHOULD-NOT-BE-IN-METADATA-PROMPT" not in client.summary_calls[0]["text"]
    assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")
```

- [ ] **Step 2: Add failing test proving no heuristic metadata fallback**

```python
def test_openai_summary_adapter_uses_defaults_without_heuristic_metadata_fallback() -> None:
    class EmptyMetadataClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract bibliographic metadata from the first-two-pages OCR/text"):
                return "{}"
            return "generated summary"

    client = EmptyMetadataClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    card = adapter.summarize_paper(
        "Nature 2025 Corresponding author: person@lab.org",
        {"slug": "papers/test-paper", "title": "Seed Title"},
    )

    assert card["title"] == "Seed Title"
    assert card["authors"] == []
    assert card["journal"] == "Unknown"
    assert card["year"] == 0
    assert card["corresponding_authors"] == []
```

- [ ] **Step 3: Run targeted tests to confirm failures**

Run: `python3 -m pytest tests/test_openai_adapter.py -k "first_from_two_page_window or defaults_without_heuristic" -v`  
Expected: FAIL because current adapter still uses first-page framing + heuristic metadata fallbacks.

- [ ] **Step 4: Commit red-phase metadata tests**

```bash
git add tests/test_openai_adapter.py
git commit -m "test: add failing metadata-first extraction coverage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Implement metadata-first LLM extraction without heuristic fallback

**Files:**
- Modify: `paperbrain/adapters/llm.py:81-845`
- Modify: `tests/test_openai_adapter.py:430-760`
- Test: `tests/test_openai_adapter.py`

- [ ] **Step 1: Expand `_infer_bibliographic_fields` contract to include title and corresponding_authors from first-two-pages window**

```python
def _infer_bibliographic_fields(self, *, seed_title: str, first_two_pages_text: str) -> dict:
    prompt = (
        "Extract bibliographic metadata from the first-two-pages OCR/text.\n"
        "Role: You are a precise scientific metadata extraction assistant.\n"
        "Objective: Extract bibliographic metadata from first-two-pages OCR text.\n"
        "Evidence boundary: Use only the text provided below; do not use outside knowledge.\n"
        "Output contract: Return strict JSON object only with keys title (string), authors (array of strings), "
        "journal (string), year (integer), corresponding_authors (array of strings).\n"
        "Defaults/failure policy: If unknown, use title=\"\", authors=[], journal=\"\", year=0, corresponding_authors=[].\n\n"
        f"Seed title: {seed_title}\n\n"
        f"{first_two_pages_text[:8000]}"
    )
    raw = self.client.summarize(prompt, model=self.model)
    parsed = self._extract_json_object(raw)
    return {
        "title": str(parsed.get("title", "")).strip(),
        "authors": self._as_string_list(parsed.get("authors")),
        "journal": str(parsed.get("journal", "")).strip(),
        "year": self._coerce_year(parsed.get("year")),
        "corresponding_authors": self._as_string_list(parsed.get("corresponding_authors")),
    }
```

- [ ] **Step 2: Refactor `summarize_paper` to run metadata-first and remove heuristic fallback usage**

```python
def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
    seed_title = str(metadata.get("title", "")).strip() or "Untitled"
    paper_type = str(metadata.get("paper_type", "article")).strip().lower()
    if paper_type not in {"article", "review"}:
        paper_type = "review" if "review" in seed_title.casefold() else "article"

    first_two_pages_text = paper_text[:8000]
    inferred = self._infer_bibliographic_fields(seed_title=seed_title, first_two_pages_text=first_two_pages_text)

    title = inferred["title"] or seed_title
    authors = inferred["authors"]
    journal = inferred["journal"] or "Unknown"
    year = inferred["year"]
    corresponding_authors = self._merge_unique(
        [normalize_email(author) or str(author).strip() for author in inferred["corresponding_authors"]]
    )

    summary, paper_type = self._build_summary(title=title, paper_type=paper_type, paper_text=paper_text)
    return {
        "slug": metadata["slug"],
        "type": "article",
        "paper_type": paper_type,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "summary": summary,
        "corresponding_authors": corresponding_authors,
    }
```

- [ ] **Step 3: Remove now-unused heuristic metadata helpers and stale tests tied to old fallback behavior**

```python
# In paperbrain/adapters/llm.py, delete these methods entirely:
#   _extract_year, _extract_journal, _extract_authors, _infer_corresponding_authors
# and delete any callsites in summarize_paper.
#
# In tests/test_openai_adapter.py, replace old fallback-email expectations:
assert len(client.summary_calls) == 2
assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-two-pages OCR/text")
assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")
assert all(
    not call["text"].startswith("Extract corresponding author email addresses")
    for call in client.summary_calls
)
```

- [ ] **Step 4: Run adapter tests**

Run: `python3 -m pytest tests/test_openai_adapter.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit metadata extraction refactor**

```bash
git add paperbrain/adapters/llm.py tests/test_openai_adapter.py
git commit -m "feat: switch to metadata-first llm extraction for paper cards" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Full verification and polish

**Files:**
- Modify: `tests/test_ingest_service.py` (only if assertion tuning is needed)
- Modify: `tests/test_openai_adapter.py` (only if assertion tuning is needed)
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_openai_adapter.py`
- Test: full suite

- [ ] **Step 1: Run focused suite for changed components**

Run: `python3 -m pytest tests/test_ingest_service.py tests/test_openai_adapter.py -q`  
Expected: PASS.

- [ ] **Step 2: Run full project test suite**

Run: `python3 -m pytest -q`  
Expected: PASS (allow existing skipped tests).

- [ ] **Step 3: Commit any final test-only adjustments (if needed)**

```bash
git add tests/test_ingest_service.py tests/test_openai_adapter.py
git commit -m "test: finalize ingest and metadata regression assertions" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
