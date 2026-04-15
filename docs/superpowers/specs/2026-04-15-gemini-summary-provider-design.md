# Gemini Summary Provider Support Design

## Problem statement

PaperBrain currently assumes OpenAI for both embeddings and summary generation. We need Gemini model API support for summary generation while keeping embeddings on OpenAI.

## Scope

In scope:
1. Add Gemini summary-provider support selected automatically by summary model name.
2. Keep OpenAI embeddings as the only embedding provider.
3. Add `gemini_api_key` to configuration and setup flow.
4. Add provider-aware setup validation and runtime wiring tests.
5. Update docs and command examples to show Gemini summary usage.

Out of scope:
1. Gemini embeddings support.
2. Automatic provider fallback on provider failure.
3. Changes to card schemas, link tables, or web UI behavior.

## Approved approach

Implement a separate Gemini summary client/adapter and route by summary model prefix.

Rationale:
1. Clear provider boundaries and minimal impact on working OpenAI paths.
2. Keeps embedding pipeline unchanged and schema-safe.
3. Easier to test than mixed branching inside existing OpenAI client.

## Architecture/components

1. **`paperbrain/adapters/gemini_client.py` (new)**
   - Lightweight client with `summarize(text, model)` using Google Generative AI SDK.
2. **`paperbrain/adapters/llm.py`**
   - Add `GeminiSummaryAdapter` implementing the same `LLMAdapter` behavior as `OpenAISummaryAdapter`.
   - Reuse current prompt/JSON parsing/validation logic to keep card outputs consistent.
3. **`paperbrain/config.py`**
   - Extend `AppConfig` with `gemini_api_key`.
   - Update `ConfigStore.save/load` for new key with backward-compatible default `""`.
4. **`paperbrain/services/setup.py`**
   - Add provider-aware summary validation:
     - OpenAI summary model -> validate via OpenAI client.
     - Gemini summary model -> validate via Gemini client.
   - Always validate embeddings through OpenAI client.
5. **`paperbrain/cli.py`**
   - Runtime adapter factory routes summary provider by model prefix:
     - `summary_model.startswith("gemini-")` -> `GeminiSummaryAdapter`.
     - else -> existing OpenAI adapter.
   - `setup` command accepts `--gemini-api-key` and passes it to setup service.

## Data flow

1. `paperbrain setup` writes `openai_api_key`, `gemini_api_key`, `summary_model`, `embedding_model`.
2. Connection test path:
   - DB always validated.
   - OpenAI embedding probe always validated.
   - Summary probe validated by selected provider.
3. `paperbrain summarize` builds runtime:
   - Embedding adapter remains OpenAI.
   - Summary adapter selected by summary model prefix.
4. Downstream summarize service/card generation remains unchanged regardless of provider.

## Error handling

1. Missing selected-provider key fails fast with clear error:
   - Gemini model with empty `gemini_api_key` -> setup/runtime error.
   - OpenAI model with empty `openai_api_key` -> existing behavior.
2. Provider validation errors are wrapped with setup context, preserving current error style.
3. No silent fallback to another provider when selected provider fails.

## Testing strategy

1. **Config tests (`tests/test_config.py`)**
   - Save/load `gemini_api_key`.
   - Backward-compatible load for configs missing `gemini_api_key`.
2. **Setup tests (`tests/test_setup_command.py`)**
   - `run_setup` validates summary provider based on summary model.
   - CLI setup accepts `--gemini-api-key`.
   - Missing selected-provider key errors are explicit.
3. **Adapter tests (`tests/test_openai_adapter.py` + new Gemini adapter tests)**
   - Gemini client summarize call and response extraction behavior.
   - Existing OpenAI adapter contract remains green.
4. **CLI runtime tests**
   - Runtime construction picks Gemini summary adapter when `summary_model` starts with `gemini-`.
   - Non-Gemini summary models continue using OpenAI summary adapter.

## Documentation updates

1. README config example includes `gemini_api_key`.
2. README setup examples include optional `--gemini-api-key`.
3. Clarify provider selection rule: summary provider selected by summary model prefix.

## Acceptance criteria

1. User can run with Gemini summary model (for example `gemini-2.5-flash`) and generate cards successfully.
2. Embeddings remain OpenAI-backed and keep 1536-dimension schema compatibility.
3. Existing OpenAI-only workflows continue working without behavior change.
4. Setup and runtime produce clear errors for missing selected-provider credentials.
5. New and updated tests pass.
