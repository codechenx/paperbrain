# Ingest Section Trimming and Corresponding-Author Format Design

## Problem statement

PaperBrain currently removes image payloads and reference sections from ingested full text, but still keeps other non-essential back-matter sections that increase token usage (`Author contributions`, `Acknowledgements`, `Competing interests`).

Also, paper-card `corresponding_authors` currently collapses entries to plain emails in summary output, while the desired output is author identity strings in `Name <email>` form.

## Scope

In scope:
1. Expand end-section trimming in ingest cleanup to include:
   - `Author contributions`
   - `Acknowledgements`
   - `Competing interests`
   - existing reference-family headings
2. Keep metadata truncation for metadata extraction only.
3. Keep full-text input for paper summary generation.
4. Update metadata prompt contract to request `Name <email>` formatting for corresponding authors.
5. Preserve name+email format in paper-card `corresponding_authors` (do not normalize to email-only).
6. Add regression tests for ingest trimming and corresponding-author formatting.

Out of scope:
1. Changing topic/person validation logic.
2. Altering schema or card link-table structure.
3. Redesigning LLM retry strategy.

## Approved design

### 1. Architecture/components

1. **Ingest (`paperbrain/adapters/docling.py`)**
   - Extend heading-matching logic used by trim-to-end behavior.
   - Trimming starts at the earliest matching heading among:
     references-family + new back-matter headings.
2. **LLM summary adapter (`paperbrain/adapters/llm.py`)**
   - Keep metadata extraction bounded by existing metadata truncation limit.
   - Keep summary prompt on full text.
   - Update metadata prompt wording to require corresponding-author entries as `Name <email>`.
   - Preserve author strings when names are present (instead of collapsing to email-only).

### 2. Data flow

1. Ingest:
   - PDF → markdown cleanup (images removed, end sections trimmed) → `papers.full_text`.
2. Summarize:
   - Metadata extraction prompt gets truncated text window.
   - Summary prompt gets full `paper_text`.
   - `corresponding_authors` in paper card reflects `Name <email>` format when provided by model.

### 3. Error handling

1. Existing strict validation rules stay unchanged for person/topic generation.
2. No silent fallback additions.
3. If LLM returns plain emails, values remain accepted strings; the adapter must not strip names when names are present.

### 4. Testing

1. `tests/test_ingest_service.py`
   - Add/extend coverage that ingest trimming removes:
     - `Author contributions`
     - `Acknowledgements`
     - `Competing interests`
     - existing references headings
2. `tests/test_openai_adapter.py`
   - Add/extend coverage for updated metadata prompt contract language.
   - Verify paper-card `corresponding_authors` preserves `Name <email>` strings.
   - Keep regression coverage for metadata truncation + full-summary behavior.

## Acceptance criteria

1. Ingested `papers.full_text` excludes image payloads, references, author-contribution, acknowledgements, and competing-interest sections by trim-to-end behavior.
2. Metadata extraction remains truncated; summary generation remains full-text.
3. Paper-card `corresponding_authors` keeps `Name <email>` formatting when available and is no longer reduced to email-only.
4. New/updated tests cover the above behavior and pass with existing suite.
