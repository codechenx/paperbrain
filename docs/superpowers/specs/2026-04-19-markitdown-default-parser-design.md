# MarkItDown Default Parser (Marker Replacement) Design

## Problem

PaperBrain currently defaults to Marker for PDF ingest and validates `pdf_parser` as `marker|docling`.  
The new requirement is to replace Marker with Microsoft MarkItDown as the default parser, keep Docling as the alternate parser, and remove Marker support.

## Goals

1. Make `markitdown` the default `pdf_parser`.
2. Support only `markitdown` and `docling` as valid parser values.
3. Preserve existing parser-worker memory behavior (one converter instance per worker process).
4. Keep unified OCR contract via `ocr_enabled`.
5. Fail fast with clear guidance when OCR is requested for MarkItDown but OCR capability is unavailable.

## Non-Goals

1. No backward-compatibility alias from `marker` to `markitdown`.
2. No silent fallback when OCR is enabled but MarkItDown OCR dependencies are missing.
3. No CLI subprocess wrapper for `markitdown`; use Python adapter integration.

## Proposed Architecture

### Parser Adapter Layer

- Add `paperbrain/adapters/markitdown.py` implementing the parser contract used by ingest.
- Adapter responsibilities:
  - initialize MarkItDown converter (`create_converter()`)
  - parse a PDF with converter reuse (`parse_pdf_with_converter(...)`)
  - normalize result into `ParsedPaper`
  - enforce OCR fail-fast rule for MarkItDown when `ocr_enabled=True` and OCR capability is not available

### Parser Factory

- Update `build_pdf_parser(...)` to return:
  - `MarkItDownParser` for `markitdown`
  - `DoclingParser` for `docling`
- Remove Marker construction path and marker-specific error text.

### Config Contract

- Set `DEFAULT_PDF_PARSER = "markitdown"`.
- Set `SUPPORTED_PDF_PARSERS = {"markitdown", "docling"}`.
- Keep `pdf_parser` required.
- Reject `pdf_parser = "marker"` with explicit migration guidance to `markitdown`.

### Worker Behavior

- Keep `ParserParseWorker` process model and handshake protocol unchanged.
- Reuse a single MarkItDown converter instance per worker via existing `create_converter()` + `parse_pdf_with_converter()` path.

## Runtime Flow

1. Config load validates parser value (`markitdown|docling`).
2. Runtime builds parser via `build_pdf_parser(...)`.
3. Ingest worker starts parser, creates converter once if supported.
4. Each parse request uses the parser and converter-reuse path.
5. Parse result is returned as normalized `ParsedPaper`.

## OCR Behavior

### `pdf_parser=markitdown`

- `ocr_enabled=false`: use base MarkItDown PDF conversion.
- `ocr_enabled=true`: validate OCR support at parser initialization and fail fast if unavailable, with installation guidance for OCR plugin/dependencies.

### `pdf_parser=docling`

- Existing docling OCR behavior remains unchanged.

## Dependencies

1. Replace Marker package dependency with MarkItDown PDF dependency (`markitdown[pdf]` equivalent in project dependency form).
2. Do not include OCR plugin dependency by default.
3. OCR plugin remains optional and user-installed when OCR is requested.

## Documentation Changes

1. Update README dependency list and setup examples to `markitdown` default.
2. Update parser-option documentation to `markitdown|docling`.
3. Document OCR plugin requirement for MarkItDown when `ocr_enabled=true`.
4. Remove Marker-specific setup/usage references.

## Error Handling

1. Invalid parser value: clear allowed values and migration guidance.
2. MarkItDown package missing: explicit install instruction.
3. MarkItDown OCR requested but unavailable: explicit fail-fast error with install guidance.
4. Worker startup errors continue to surface parser init failures via existing startup handshake.

## Testing Strategy

1. Config tests:
   - default parser is `markitdown`
   - `markitdown`/`docling` accepted
   - `marker` rejected with actionable error
2. Parser factory tests:
   - `markitdown` returns `MarkItDownParser`
   - `docling` returns `DoclingParser`
   - invalid values rejected
3. MarkItDown adapter tests:
   - missing dependency error
   - OCR fail-fast path
   - conversion normalization behavior
4. Worker tests:
   - startup/parse flow with `markitdown`
   - converter reuse path with `markitdown`
5. Setup/CLI wiring tests:
   - parser options and defaults updated
   - ingest worker receives `markitdown` by default

## Rollout Notes

1. Existing configs with `pdf_parser="marker"` must be edited to `pdf_parser="markitdown"`.
2. No compatibility alias is provided by design to keep parser behavior explicit and predictable.
