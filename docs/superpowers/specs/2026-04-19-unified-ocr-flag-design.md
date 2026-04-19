# Unified OCR Flag for Marker + Docling Design

## Problem

OCR control is currently Docling-specific (`docling_ocr_enabled`). With Marker now supported, OCR should be controlled by one shared setting regardless of parser.

## Goal

Introduce a single required config flag `ocr_enabled` used by both Marker and Docling, defaulting to disabled, and remove `docling_ocr_enabled` from the config contract.

## Approved Decisions

1. Use one shared required boolean flag: `ocr_enabled`.
2. `paperbrain setup` uses `--ocr-enabled/--no-ocr-enabled`.
3. Both parsers consume the same OCR flag.
4. `ocr_enabled` missing in config is invalid.
5. Old `docling_ocr_enabled`-only configs are invalid (no compatibility fallback).

## Approaches Considered

1. **Hard rename to unified OCR flag (chosen)**
   - Replace all `docling_ocr_enabled` plumbing with `ocr_enabled`.
   - Pros: clean model, parser-agnostic, aligns exactly with requirement.
   - Cons: breaking change for existing configs.

2. Backward-compatible alias
   - Read old `docling_ocr_enabled` as fallback.
   - Pros: softer migration.
   - Cons: contradicts strict invalid-old-key requirement.

3. Per-parser OCR flags
   - Keep separate parser-specific options.
   - Pros: more granular control.
   - Cons: unnecessary complexity for current use case.

## File-Level Design

- `paperbrain/config.py`
  - Replace `DEFAULT_DOCLING_OCR_ENABLED` usage with `DEFAULT_OCR_ENABLED`.
  - Extend `AppConfig` with `ocr_enabled: bool`.
  - Persist `ocr_enabled` in `ConfigStore.save`.
  - Require `ocr_enabled` in `ConfigStore.load` and reject invalid type.
  - Remove load/save reliance on `docling_ocr_enabled`.

- `paperbrain/services/setup.py`
  - Rename `run_setup(..., docling_ocr_enabled=...)` to `run_setup(..., ocr_enabled=...)`.
  - Pass unified flag to config persistence.

- `paperbrain/cli.py`
  - Rename setup option to `--ocr-enabled/--no-ocr-enabled`.
  - Pass `ocr_enabled` to `run_setup`.

- `paperbrain/adapters/parser_factory.py`
  - Rename signature to `build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool)`.
  - Pass `ocr_enabled` to `DoclingParser(ocr_enabled=...)`.
  - Pass `ocr_enabled` to `MarkerParser(ocr_enabled=...)`.

- `paperbrain/adapters/marker.py`
  - Add `ocr_enabled` constructor parameter.
  - Wire to Marker conversion configuration using `force_ocr=True` when enabled.
  - Keep default OCR off.

- `paperbrain/summary_provider.py`
  - Use unified `config.ocr_enabled` when constructing parser via factory.

- Tests
  - `tests/test_config.py`: require `ocr_enabled`, reject missing/invalid field, remove legacy-key expectations.
  - `tests/test_setup_command.py`: setup flag rename and runtime plumbing updates.
  - `tests/test_summary_provider.py`: ensure parser factory receives `ocr_enabled`.
  - `tests/test_parser_factory.py`: validate unified `ocr_enabled` wiring.
  - `tests/test_marker_parser.py`: assert Marker OCR config toggles with flag.

- `README.md`
  - Update setup examples, config shape, and OCR behavior section for unified flag.

## Data Flow

1. User runs `paperbrain setup --ocr-enabled` (or default `--no-ocr-enabled`).
2. Config persists required `ocr_enabled = true|false`.
3. Runtime loads config and validates `ocr_enabled`.
4. Parser factory applies the same OCR flag to selected parser.
5. Parsing proceeds with OCR disabled by default for both parsers.

## Error Handling

- Missing `ocr_enabled` in config raises clear `ValueError`.
- Invalid non-boolean `ocr_enabled` raises clear `ValueError`.
- Marker dependency errors remain fail-fast with install guidance.

## Backward Compatibility

- Breaking by design: config files that only contain `docling_ocr_enabled` are invalid.
- Users must re-run setup or manually update config to include `ocr_enabled`.

## Testing Strategy

1. Config contract tests for required `ocr_enabled`.
2. Setup CLI tests for renamed option and pass-through.
3. Runtime parser factory tests for shared OCR wiring.
4. Marker adapter tests verifying OCR-off default and OCR-on mapping.
5. Full regression suite to ensure ingest/search/summarize behavior remains stable.

## Out of Scope

- Keeping legacy alias support for `docling_ocr_enabled`.
- Parser-specific OCR knobs beyond one shared boolean.
- Additional Marker LLM/advanced OCR tuning flags.
