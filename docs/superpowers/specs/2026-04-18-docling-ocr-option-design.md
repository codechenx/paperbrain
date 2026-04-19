# Docling OCR Toggle Design

## Problem

Docling OCR behavior is not configurable. Users need an explicit option to control OCR use and keep it disabled by default.

## Goal

Add a persistent configuration option that controls Docling OCR, with default `false`, and wire it through setup/config/provider/parser so ingest behavior follows config.

## Approved Approach

1. Add `docling_ocr_enabled: bool` to runtime config (`AppConfig`).
2. Add setup/config persistence using `--docling-ocr-enabled/--no-docling-ocr-enabled` (default disabled).
3. Update parser construction to pass the configured OCR toggle.
4. Apply toggle at Docling converter construction time.

## File-Level Design

- `paperbrain/config.py`
  - Extend `AppConfig` with `docling_ocr_enabled`.
  - `ConfigStore.save(...)` writes `docling_ocr_enabled`.
  - `ConfigStore.load()` requires `docling_ocr_enabled` and `embeddings_enabled`, both boolean.

- `paperbrain/services/setup.py`
  - Accept `docling_ocr_enabled` and persist it.

- `paperbrain/cli.py`
  - `setup` command exposes `--docling-ocr-enabled/--no-docling-ocr-enabled`.
  - Default remains disabled.

- `paperbrain/summary_provider.py`
  - Build parser as `DoclingParser(ocr_enabled=config.docling_ocr_enabled)`.

- `paperbrain/adapters/docling.py`
  - Add parser-level OCR toggle state.
  - Use the toggle when creating `DocumentConverter`.

## Behavior Notes

- No backward compatibility for legacy config files missing either `docling_ocr_enabled` or `embeddings_enabled`.
- Ingest does not get an override flag; it always follows persisted config.

## Error Handling

- If `docling_ocr_enabled` or `embeddings_enabled` is missing/non-boolean in config, raise clear `ValueError`.
- Existing Docling import errors remain explicit.

## Testing Strategy

1. Config tests: save/load default false and explicit true, and missing-key failure for both flags.
2. Setup/CLI tests: setup option wiring and persisted value.
3. Parser/provider tests: parser receives configured toggle and converter wiring uses it.
