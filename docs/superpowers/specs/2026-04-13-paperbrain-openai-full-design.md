# PaperBrain Full Implementation Design (OpenAI + Postgres + Docling)

## Problem

The current repository contains a scaffolded PaperBrain CLI. We need a full implementation that executes real workflows with:

- Postgres + pgvector persistence
- Real PDF ingestion
- Hybrid retrieval (keyword + vector)
- OpenAI-backed summarization/embedding
- Card generation for paper/person/topic
- Data linting, stats, and markdown export

The implementation must support real testing using a configured OpenAI key and local PDFs.

## Goals

1. Implement all core commands with real behavior:
   - `setup`, `init`, `ingest`, `browse`, `search`, `summarize`, `lint`, `stats`, `export`
2. Persist runtime config in `./config/paperbrain.conf`, including:
   - `database_url`
   - `openai_api_key`
   - `summary_model` (default `gpt-4.1-mini`)
   - `embedding_model` (default `text-embedding-3-small`)
3. Use real Postgres/pgvector schema and queries for ingestion/search/card storage.
4. Use real OpenAI API calls in adapter implementation, with optional live tests.
5. Keep offline tests deterministic and stable.

## Architecture

### CLI Layer

`paperbrain/cli.py` remains the command surface and delegates to service functions/classes. CLI never embeds raw SQL or API calls.

### Services Layer

`paperbrain/services/` orchestrates each workflow:

- `setup`: validate and persist config
- `init`: initialize/rebuild database schema
- `ingest`: discover PDFs, parse, chunk, embed, store
- `search` and `browse`: keyword/hybrid retrieval
- `summarize`: generate/update paper/person/topic cards
- `lint`: quality checks and deterministic fixes
- `stats`: corpus metrics
- `export`: markdown artifact generation

### Infrastructure Layer

- `paperbrain/db.py`: psycopg connection management, transactions, schema SQL, query helpers
- `paperbrain/repositories/*` (new): persistence APIs by domain
- `paperbrain/adapters/docling.py`: real Docling PDF extraction
- `paperbrain/adapters/openai_client.py` (new): OpenAI wrapper for embeddings and summaries

## Data Model

Core tables:

- `papers`
- `paper_chunks`
- `paper_embeddings` (pgvector)
- `paper_cards`
- `person_cards`
- `topic_cards`
- link tables: `paper_person_links`, `paper_topic_links`, `person_topic_links`

Indexing:

- full-text indexes on searchable text fields
- vector index on embeddings
- unique/foreign-key indexes on slugs and relations

## Data Flow

1. **Setup**
   - Accept DB URL and OpenAI key + models.
   - Validate connectivity and credentials.
   - Write `./config/paperbrain.conf`.

2. **Init**
   - Apply schema SQL.
   - `--force` drops and recreates schema in dependency-safe order.

3. **Ingest**
   - Traverse input path(s) for PDFs.
   - Extract metadata/text via Docling.
   - Normalize metadata; compute paper slug.
   - Chunk text.
   - Request embeddings from OpenAI.
   - Upsert paper/chunks/embeddings.

4. **Search/Browse**
   - Browse: keyword query across card stores by type.
   - Search: combine keyword rank + vector similarity into hybrid score and return top-k.
   - Optional card inclusion joins paper/person/topic cards.

5. **Summarize**
   - Generate paper cards from papers/chunks using OpenAI.
   - Derive/update person cards from corresponding authors.
   - Derive/update topic cards from person big-question clusters.
   - Persist bidirectional links.

6. **Lint/Stats/Export**
   - Lint whitespace, metadata consistency, and dead links.
   - Stats aggregate corpus counts/coverage.
   - Export markdown files to Obsidian-style structure with bidirectional wikilinks.

## Error Handling

- All command failures return non-zero exits with explicit messages.
- No broad catch-and-ignore patterns.
- API/DB/parser errors are surfaced with context (paper path/slug/command stage).
- Sensitive data is never emitted (API key redaction by default).

## Testing Strategy

### Deterministic tests (default)

- Unit tests for slugging, config read/write, scoring, linting, exporters.
- Service tests with mocked adapters and in-memory fakes.

### Optional live tests (explicit opt-in)

- Enabled only when `PAPERBRAIN_LIVE_TEST=1`.
- Require `OPENAI_API_KEY` and reachable Postgres URL.
- Use `tests/pdf/*.pdf` as input for ingest/summarize/search smoke assertions.

This keeps normal test runs stable while allowing real end-to-end verification.

## Scope Boundaries

In scope:

- Full command behavior and wiring
- Real OpenAI + Postgres + Docling integration
- Optional live test harness
- Markdown export with cross-linking

Out of scope:

- Production job queue/distributed execution
- Multi-tenant auth layer
- Advanced migration framework beyond current schema bootstrap

