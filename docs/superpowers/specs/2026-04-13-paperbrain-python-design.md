# PaperBrain Python Project Design

## Problem

Build a Python CLI project that implements the PaperBrain workflow in `Design.md`: local PDF ingestion, hybrid search (keyword + vector), card generation (paper/person/topic), data linting, corpus stats, and markdown export for Obsidian.

## Chosen Approach

Use a modular package architecture with clean interfaces for external dependencies (Docling parsing and LLM summarization), while fully wiring CLI commands, DB schema, services, and export flow.

## Architecture

### CLI layer

- `paperbrain setup`
- `paperbrain init`
- `paperbrain ingest`
- `paperbrain browse`
- `paperbrain search`
- `paperbrain summarize`
- `paperbrain lint`
- `paperbrain stats`
- `paperbrain export`

Each command maps to a service method and returns explicit success/failure exit codes.

### Core modules

- `paperbrain/config.py`: load and persist config (`~/.config/paperbrain.conf`)
- `paperbrain/db.py`: DB connection and bootstrap/migration helpers
- `paperbrain/models.py`: dataclasses / typed structures for papers/cards/results
- `paperbrain/services/`: ingest, search, summarize, lint, stats, export orchestration
- `paperbrain/adapters/docling.py`: PDF parsing adapter interface + default adapter
- `paperbrain/adapters/llm.py`: summarization/profile adapter interface + default adapter
- `paperbrain/quality.py`: data quality checks and auto-fixes
- `paperbrain/exporter.py`: Obsidian markdown rendering and file layout

## Data Model (Postgres + pgvector)

- `papers`: metadata and canonical paper body references
- `paper_chunks`: chunked text units for retrieval
- `paper_embeddings`: vector embeddings for chunks (`vector` column)
- `paper_cards`: generated paper summaries
- `person_cards`: corresponding-author profiles
- `topic_cards`: grouped topic profiles
- relationship/link tables for bidirectional references:
  - paper <-> person
  - paper <-> topic
  - person <-> topic

Indexes include:

- full text (`tsvector`) for keyword search
- ivfflat/hnsw vector index for embedding similarity
- lookup indexes for slugs and foreign keys

## Data Flow

1. `ingest`: discover PDFs (file or recursive directory), parse via Docling adapter, chunk text, persist papers/chunks, generate/store embeddings.
2. `search`: execute hybrid score combining BM25/FTS rank and vector similarity; return top-k papers with optional related cards.
3. `browse`: keyword lookup over card titles/content by type (paper/person/topic/all).
4. `summarize`: call LLM adapter to generate/update paper cards, then derive person/topic cards and relationship links.
5. `lint`: run data quality checks (whitespace, dead links, missing metadata) and apply deterministic fixes.
6. `stats`: aggregate corpus counts and coverage.
7. `export`: render markdown files to Obsidian-style structure with bidirectional links.

## Error Handling

- Fail fast for invalid config, DB errors, missing adapters, parser/LLM failures.
- Surface actionable command errors with non-zero exit status.
- Keep adapter failures explicit (no silent drops).

## Testing Strategy

- Unit tests:
  - slug/normalization helpers
  - config round-trip
  - quality fix rules
  - search score blending
- Integration tests:
  - CLI command routing and options
  - ingest/search/summarize/export pipelines with mocked adapters
- SQL/schema tests:
  - bootstrap creates required tables/indexes
  - key constraints and relationships hold

## Scope Boundaries

In scope for this implementation:

- Full command surface and wiring
- Postgres schema bootstrap
- Pluggable adapter contracts and default implementations
- Markdown export structure and links

Out of scope:

- Production tuning of embedding/LLM models
- Advanced migration framework beyond bootstrap SQL

