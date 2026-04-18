# Optional Embeddings (Default Disabled) Design

## Problem

PaperBrain currently assumes embeddings are always enabled, which forces an OpenAI key and full embedding generation during ingest. The requested behavior is to make embeddings optional and disabled by default.

## Goals

1. Embeddings are disabled by default.
2. OpenAI key is only required when needed (OpenAI summaries or embeddings enabled).
3. Ingest works without embeddings.
4. Search falls back to keyword-only mode when embeddings are disabled.
5. Existing enabled-embedding flows remain unchanged.

## Proposed Approach

Add an explicit config toggle:

- `embeddings_enabled: bool = false` (new)
- `embedding_model: str` remains configurable, only used when `embeddings_enabled=true`

Runtime behavior:

- Build runtime with `embeddings=None` when disabled.
- Require OpenAI key only if:
  - `summary_model` uses `openai:*`, or
  - `embeddings_enabled=true`

Service behavior:

- Ingest:
  - Always parse/store papers and chunks.
  - If embeddings disabled, skip embedder call and do not write to `paper_embeddings`.
- Search:
  - If embeddings enabled, keep hybrid search behavior.
  - If embeddings disabled, run keyword-only search and keep response shape with `vector_rank=0`.

## Data and Interface Changes

1. Config layer (`paperbrain/config.py`)
   - Extend `AppConfig` with `embeddings_enabled`.
   - Save/load `embeddings_enabled`, default false for new and legacy configs.
   - Validate `embedding_model` only when embeddings are enabled.

2. Setup/CLI (`paperbrain/services/setup.py`, `paperbrain/cli.py`)
   - Add `--embeddings-enabled/--no-embeddings-enabled` option, default disabled.
   - Connection tests for embedding endpoint run only when embeddings are enabled.
   - OpenAI key prompting/validation aligned with conditional requirements.

3. Runtime provider (`paperbrain/summary_provider.py`)
   - Create OpenAI embedding adapter only when embeddings enabled.
   - Keep LLM summary provider routing unchanged.

4. Ingest (`paperbrain/services/ingest.py`, `paperbrain/repositories/postgres.py`)
   - Allow ingest service to operate with optional embedder.
   - Add repository path that replaces chunks even when vectors are omitted.

5. Search (`paperbrain/services/search.py`, `paperbrain/repositories/postgres.py`)
   - Add keyword-only repository query.
   - Route to keyword-only path when embedder is absent.

## Error Handling

- Clear error if embeddings are enabled but no OpenAI key is configured.
- Clear error if OpenAI summary provider is selected without OpenAI key.
- Avoid silent fallback when embeddings are explicitly enabled but misconfigured.

## Testing Plan

1. Config:
   - Default `embeddings_enabled` is false.
   - Legacy config without the field loads with embeddings disabled.
   - Embedding model validation only enforced when embeddings enabled.

2. Setup/CLI/runtime:
   - OpenAI key not required for Gemini/Ollama summaries when embeddings disabled.
   - OpenAI key required when OpenAI summary model is selected.
   - OpenAI key required when embeddings enabled.

3. Ingest:
   - Ingest succeeds with embeddings disabled and writes chunks without vectors.
   - Existing embedding-enabled ingest path remains unchanged.

4. Search:
   - Keyword-only results when embeddings disabled.
   - Existing hybrid behavior unchanged when embeddings enabled.

## Scope Boundaries

In scope:
- Config/runtime/setup/ingest/search behavior updates for optional embeddings.

Out of scope:
- Schema redesign away from `paper_embeddings`.
- Changing summary provider selection semantics.
