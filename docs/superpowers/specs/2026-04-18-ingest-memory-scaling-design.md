# Ingest Memory Scaling Design (1000+ PDFs)

## Problem

Large ingest runs can exhaust memory when Docling processes many PDFs in one long session and the ingest path accumulates parse/chunk/vector data.

## Goal

Make ingest stable for 1000+ PDFs by isolating Docling memory, streaming processing, and adding deterministic batching controls.

## Approved Approach

1. **Process-isolated Docling worker with recycling**
   - Add a parse worker process that owns one `DocumentConverter`.
   - Worker handles one file per request and returns parsed payload.
   - Coordinator restarts worker after configurable count (`--parse-worker-recycle-every`) to release accumulated memory.

2. **Streaming ingest pipeline**
   - Process files one-by-one and persist incrementally.
   - Avoid retaining large intermediate structures across multiple papers.
   - Keep per-paper memory bounded (parse -> chunk -> embed -> write -> release).

3. **CLI batching/resume controls**
   - Add ingest options:
     - `--max-files <int>`: process at most the provided number of discovered files.
     - `--start-offset <int>`: skip the first provided number of discovered files.
     - `--parse-worker-recycle-every <int>`: restart parse worker every provided number of parsed files.
   - This enables deterministic segmented runs and safe resume from known offsets.
   - Default recycle cadence: **25** files per worker lifecycle.

## File-Level Design

- `paperbrain/adapters/docling.py`
  - Keep pure parsing logic.
  - Add a worker-facing parse entrypoint that is serializable-safe.

- `paperbrain/services/ingest.py`
  - Extend ingest service API to accept batching and worker recycle settings.
  - Orchestrate parse worker lifecycle and per-paper streaming flow.

- `paperbrain/cli.py`
  - Add new ingest flags and pass them to service.

- `tests/test_ingest_service.py`
  - Add tests for offset/limit behavior and recycle cadence.

- `tests/test_cli_commands.py` / `tests/test_setup_command.py` (where ingest CLI behavior is covered)
  - Add flag wiring/validation coverage.

## Data Flow

1. Discover files (stable sorted order, existing behavior).
2. Apply `start_offset` and `max_files`.
3. For each selected file:
   - Parse in worker process.
   - Dedupe check (`has_paper`) and skip if needed.
   - Chunk and embed current paper.
   - Persist paper + chunks/vectors.
4. If parsed count hits recycle boundary, restart worker.

## Error Handling

- If worker crashes or times out: raise clear runtime error with offending file path.
- If parse fails for one file: propagate explicit error (no silent skip).
- Validate new CLI args (`>=0`, and recycle cadence > 0 when provided).

## Backward Compatibility

- Existing ingest command remains valid without new flags.
- Default behavior for small corpora remains unchanged except memory improvements.

## Testing Strategy

1. **Unit tests (service)**
   - offset/limit selection correctness
   - worker recycle cadence triggers restart at expected intervals
   - failure path surfaces explicit file/context

2. **CLI tests**
   - flags parsed and forwarded correctly
   - invalid values produce clear errors

3. **Regression**
   - existing ingest dedupe and force behavior unchanged

## Out of Scope

- Distributed ingest execution.
- Multi-worker parallel parse/embedding.
- Database schema changes.
