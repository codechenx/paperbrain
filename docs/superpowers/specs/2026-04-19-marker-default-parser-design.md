# Marker as Default PDF Ingest Parser (with Docling Option) Design

## Problem

PDF ingest currently uses Docling directly. Users need parser choice and want Marker (`datalab-to/marker`) as the default parser while still supporting Docling.

## Goal

Add persistent parser selection in setup/config, default to Marker, keep Docling as an explicit alternative, and preserve the existing `ParsedPaper` output behavior for ingest.

## Approved Decisions

1. Parser choice is **persistent config**, not per-run ingest override.
2. Marker is the **default parser**.
3. If Marker is selected but unavailable, ingest must **fail fast** with a clear install error.
4. Marker output must keep metadata behavior aligned with current Docling heuristics.
5. Existing config files missing parser field default to Marker on load.

## Approaches Considered

1. **Config + parser factory + adapter boundary (chosen)**
   - Add `pdf_parser` config field (`marker|docling`), build parser via centralized factory.
   - Pros: explicit, testable, clean extension point.
   - Cons: touches setup/config/runtime wiring in multiple files.

2. Marker-first with Docling legacy branches
   - Inline branching around Marker and Docling in runtime paths.
   - Pros: fewer new abstractions.
   - Cons: harder to maintain; logic spread across call sites.

3. Runtime branching inside provider/CLI only
   - Avoid factory, add direct `if/else` in existing runtime constructors.
   - Pros: quick.
   - Cons: parser selection policy duplicated and less composable.

## File-Level Design

- `paperbrain/config.py`
  - Add `DEFAULT_PDF_PARSER = "marker"` and allowed parser values.
  - Extend `AppConfig` with `pdf_parser: str`.
  - Persist `pdf_parser` in `ConfigStore.save`.
  - Load `pdf_parser` with default Marker when missing; validate allowed values.

- `paperbrain/services/setup.py`
  - Add `pdf_parser` argument to `run_setup`.
  - Validate parser value and persist it via `ConfigStore.save`.

- `paperbrain/cli.py`
  - Add setup option `--pdf-parser` (choices: marker/docling) with default marker.
  - Pass parser choice to `run_setup`.
  - Keep `ingest` command interface unchanged (no parser override flag).

- `paperbrain/summary_provider.py`
  - Replace direct `DoclingParser()` construction with parser factory selection based on config.

- `paperbrain/adapters/docling.py`
  - Keep existing behavior for Docling parser.

- `paperbrain/adapters/marker.py` (new)
  - Add `MarkerParser` adapter implementing `parse_pdf(path) -> ParsedPaper`.
  - Parse via Marker package APIs and normalize into `ParsedPaper`.
  - Reuse metadata extraction behavior equivalent to current Docling heuristics.
  - Raise clear runtime error when Marker import is unavailable.

- `paperbrain/adapters/parser_factory.py` (new)
  - Central parser builder for `marker`/`docling`.
  - Raises explicit error for invalid parser values.

- Tests
  - `tests/test_config.py`: save/load parser value, missing parser defaults to marker, invalid parser rejected.
  - `tests/test_setup_command.py`: setup flag wiring and runtime parser selection.
  - `tests/test_summary_provider.py`: parser factory integration and provider wiring.
  - `tests/test_ingest_service.py` or dedicated adapter tests: Marker dependency-missing error and normalized output shape.

- `README.md`
  - Document Marker dependency and parser selection in setup/config examples.

## Data Flow

1. `paperbrain setup --pdf-parser marker|docling` writes parser choice to config.
2. Runtime loads config with `pdf_parser`; missing field defaults to `marker`.
3. Parser factory returns `MarkerParser` or `DoclingParser`.
4. Ingest service remains parser-agnostic and consumes `Parser` protocol.

## Error Handling

- Invalid `pdf_parser` in config/setup raises clear `ValueError`.
- Marker selected but package unavailable raises clear `RuntimeError` with install guidance.
- No silent fallback from Marker to Docling when Marker is selected.

## Backward Compatibility

- Existing config files without `pdf_parser` remain valid and default to Marker.
- Ingest CLI behavior remains the same except parser backend is now configurable and defaults to Marker.

## Testing Strategy

1. **Config contract**
   - Parser defaulting and validation.
2. **Setup/CLI wiring**
   - Parser flag accepted and persisted.
3. **Runtime selection**
   - Correct parser instance built from config.
4. **Marker adapter**
   - Missing dependency error path and normalized `ParsedPaper` output fields.
5. **Regression**
   - Existing ingest behavior (dedupe, force-all, chunk/vector flow) remains unchanged.

## Out of Scope

- Per-ingest parser override flag.
- Hybrid/multi-parser ingest in a single run.
- Non-PDF parser plugins beyond Marker and Docling.
