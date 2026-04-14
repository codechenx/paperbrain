# Ingest token optimization and metadata extraction redesign

## Problem statement

The current pipeline keeps image-markup noise in markdown exports, includes reference-section text in persisted full text, and still uses heuristic metadata fallbacks for bibliographic fields. This increases token usage and can reduce consistency of extracted metadata quality.

We need to:

1. Keep full paper text while removing image payload data.
2. Remove references-section text from stored full text.
3. Extract title, authors, journal, year, and corresponding authors via LLM using only first-two-pages text input.
4. Avoid heuristic fallbacks for these metadata fields.

## Scope

In scope:

1. Docling markdown post-processing in ingest parser.
2. Metadata extraction flow in OpenAI summary adapter.
3. Tests for ingest cleaning and metadata sequence/contracts.

Out of scope:

1. Person/topic card logic changes.
2. Database schema expansion for first-two-pages text persistence.
3. Non-Docling parsers.

## Approved design

### 1. Architecture/components

1. Keep persisted paper model/schema unchanged for this feature.
2. Update `DoclingParser` to return cleaned `full_text`:
   - remove image payload markers (markdown image embeds, HTML image tags, base64 image blobs),
   - keep surrounding figure/legend text,
   - trim document content starting at the first references heading (`References`, `Bibliography`, `Works Cited`).
3. Update `OpenAISummaryAdapter.summarize_paper`:
   - run metadata extraction first,
   - use a first-two-pages text window derived from `paper_text` (bounded prefix approximation),
   - extract metadata via LLM in one strict JSON call with keys:
     `title`, `authors`, `journal`, `year`, `corresponding_authors`,
   - apply defaults when missing:
     `title`: existing metadata title, else `"Untitled"`;
     `authors`: `[]`;
     `journal`: `"Unknown"`;
     `year`: `0`;
     `corresponding_authors`: `[]`,
   - do not use regex/heuristic fallback for these metadata fields.
4. Summary generation runs after metadata extraction and uses cleaned full text.

### 2. Data flow

1. Ingest:
   1. Convert PDF to markdown with Docling.
   2. Clean markdown image payloads while preserving non-image narrative text.
   3. Trim from first references-style heading through end of document.
   4. Persist cleaned `full_text`.
2. Summarize:
   1. Build first-two-pages metadata window from `paper.full_text` prefix.
   2. Call metadata LLM prompt first and normalize defaults.
   3. Call paper-summary LLM prompt second using cleaned full text.
   4. Continue existing person/topic generation flow.

### 3. Error handling

1. Keep strict JSON parsing/validation semantics for metadata and summary calls.
2. If metadata fields are absent/invalid, resolve with explicit defaults only.
3. Avoid silent heuristic corrections for metadata fields in this flow.

### 4. Testing strategy

1. `tests/test_ingest_service.py`
   - add coverage for image payload stripping with caption/legend preservation,
   - add coverage for references heading trimming across supported headings.
2. `tests/test_openai_adapter.py`
   - assert metadata prompt includes title + corresponding_authors contract,
   - assert metadata prompt input scope is first-two-pages window,
   - assert metadata extraction occurs before summary call,
   - assert no heuristic metadata fallback behavior is used.
3. Update dependent tests impacted by metadata ordering/title sourcing.

## Risks and mitigations

1. Risk: Prefix-based first-two-pages approximation may vary by document layout.
   - Mitigation: keep bounded window conservative and test with representative fixtures.
2. Risk: Aggressive references trimming could remove valid content if heading is ambiguous.
   - Mitigation: trim only on explicit section-style heading matches for approved labels.
3. Risk: Removing heuristics may reduce metadata fill rate on poor OCR.
   - Mitigation: explicit defaults and strict contract reduce bad inferred values; user can re-run with better OCR input.
