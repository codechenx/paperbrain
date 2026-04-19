# Marker Memory Optimization with Generic Parse Worker Design

## Problem

Marker ingest can consume too much system RAM during large runs because parsing happens in a long-lived process context with heavy model/converter state.

## Goal

Reduce peak RAM for large ingest batches by using process-isolated parser workers for both Marker and Docling, with frequent recycling and no behavior regressions in ingest output.

## Approved Decisions

1. Use one generic parser worker architecture for both Marker and Docling.
2. Keep and reuse `--parse-worker-recycle-every`, but default to `5` for both parsers.
3. Keep ingest flow parser-agnostic and fail-fast on parse errors.
4. Preserve existing ingest/summarize/output semantics; this is a runtime memory improvement.

## Approaches Considered

1. **Generic parser worker for all PDF parsers (chosen)**
   - Single worker protocol constructs parser by config (`pdf_parser`) and reuses converter per worker lifecycle.
   - Pros: least duplication, consistent memory behavior, extensible.
   - Cons: refactor of current Docling-only worker wiring.

2. Marker-specific worker + existing Docling worker
   - Add parallel worker implementation only for Marker.
   - Pros: faster initial patch.
   - Cons: duplicate lifecycle logic and fragmented maintenance.

3. Inline Marker optimizations only
   - Keep inline parse path, tune GC/converter reuse.
   - Pros: minimal changes.
   - Cons: weaker RAM isolation for very large ingest runs.

## File-Level Design

- `paperbrain/adapters/docling_worker.py`
  - Replace/rename to generic worker module (e.g., `parser_worker.py`) that:
    - receives parser type + OCR flag,
    - creates parser and converter once per worker lifecycle,
    - parses one file per command and returns serialized `ParsedPaper`.

- `paperbrain/adapters/parser_factory.py`
  - Expose parser construction helpers usable by runtime and worker path.

- `paperbrain/adapters/marker.py`
  - Ensure converter creation works in worker lifecycle and supports reuse.

- `paperbrain/cli.py`
  - Remove Docling-only `isinstance` worker branching.
  - Construct generic parse worker factory for both Marker and Docling parsers.
  - Change ingest option default `--parse-worker-recycle-every` to `5`.

- `paperbrain/services/ingest.py`
  - No API changes expected; keep existing parse worker lifecycle integration.

- Tests
  - `tests/test_setup_command.py`: ingest wiring verifies Marker now uses parse worker path and default recycle value.
  - `tests/test_ingest_service.py`: recycle behavior remains correct with worker factories.
  - New worker tests (or migrated from `tests/test_docling_worker.py`) for parser selection and OCR plumbing.
  - Marker-specific worker test coverage for parse command path and error propagation.

- `README.md`
  - Update ingest docs/defaults for `--parse-worker-recycle-every` to 5 and note applies to Marker and Docling.

## Data Flow

1. CLI resolves runtime config and parser selection.
2. CLI builds generic parse worker factory with selected parser type + `ocr_enabled`.
3. Ingest service streams files one-by-one:
   - worker parse -> dedupe check -> chunk/embed -> persist.
4. Worker recycles every `parse_worker_recycle_every` files (default 5), releasing parser/converter memory.

## Error Handling

- Worker parse failures return explicit error with file path context.
- Unsupported parser in worker setup raises explicit configuration/runtime error.
- Worker lifecycle shutdown/cleanup remains best-effort but deterministic.

## Backward Compatibility

- Existing ingest commands remain valid.
- Default recycle cadence changes from 25 to 5 (intentional behavior change for memory safety).
- No schema or card model changes.

## Testing Strategy

1. Worker construction tests for both parser types (`marker`, `docling`) with OCR propagation.
2. Ingest CLI wiring tests ensuring both parsers use worker factories.
3. Recycle cadence tests for default 5 and custom override.
4. Regression tests for parse error surfacing and existing ingest semantics.

## Out of Scope

- Multi-worker parallel parse.
- Distributed ingest orchestration.
- Parser-specific memory tuning flags beyond existing recycle cadence.
