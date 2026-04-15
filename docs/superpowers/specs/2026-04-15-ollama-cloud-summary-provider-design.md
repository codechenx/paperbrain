# Ollama Cloud Summary Provider Support Design

## Problem statement

PaperBrain currently supports OpenAI and Gemini for summary generation, with embeddings fixed to OpenAI. We need Ollama Cloud model API support for summary generation while preserving the existing OpenAI embedding path and schema compatibility.

## Scope

In scope:
1. Add Ollama Cloud summary-provider support selected by summary model prefix.
2. Keep OpenAI embeddings as the only embedding provider.
3. Add `ollama_api_key` and `ollama_base_url` to configuration and setup flow.
4. Add provider-aware setup validation and runtime wiring for Ollama summary models.
5. Update tests and README usage for Ollama Cloud setup.

Out of scope:
1. Ollama embeddings support.
2. Provider fallback/retry across different providers.
3. Changes to card schema, database schema, and web UI behavior.

## Approved approach

Implement a dedicated Ollama summary client/adapter and route by `summary_model` prefix `ollama:`.

Rationale:
1. Matches the existing provider-routing pattern with minimal disruption.
2. Preserves the stable OpenAI embedding pipeline and 1536-dimension storage contract.
3. Keeps provider behavior explicit and testable.

## Architecture/components

1. **`paperbrain/adapters/ollama_client.py` (new)**
   - Wrapper over official `ollama` Python SDK for summary generation.
   - Initializes client using configured base URL and Bearer auth for Ollama Cloud.
2. **`paperbrain/adapters/llm.py`**
   - Add `OllamaSummaryAdapter` that reuses the existing summarize prompt/JSON parsing contract.
3. **`paperbrain/config.py`**
   - Extend `AppConfig` with:
     - `ollama_api_key` (default empty string)
     - `ollama_base_url` (default `https://ollama.com`)
   - Update `ConfigStore.save/load` with backward-compatible defaults.
4. **`paperbrain/services/setup.py`**
   - Extend provider-aware summary validation:
     - `summary_model` prefix `ollama:` -> validate using Ollama summary client.
     - Existing OpenAI/Gemini paths unchanged.
   - OpenAI embedding validation remains mandatory.
5. **`paperbrain/cli.py`**
   - Extend runtime summary routing:
     - `summary_model.startswith("ollama:")` -> `OllamaSummaryAdapter`.
     - Strip prefix for provider model name passed to Ollama.
   - Extend `setup` command with `--ollama-api-key` and `--ollama-base-url`.

## Data flow

1. `paperbrain setup` persists `ollama_api_key` and `ollama_base_url` alongside existing config values.
2. Setup connection test path:
   - DB validation always runs.
   - OpenAI embedding validation always runs.
   - Summary validation runs against provider selected by `summary_model` prefix.
3. Runtime path (`paperbrain summarize`):
   - Embedding adapter remains OpenAI.
   - Summary adapter is selected by model prefix (`ollama:` / `gemini-` / default OpenAI).

## Error handling

1. Runtime/setup fail fast when `summary_model` uses `ollama:` but Ollama key is missing.
2. Invalid Ollama base URL or API failures surface explicit provider-context errors.
3. No silent fallback from Ollama to another provider.

## Testing strategy

1. **Config tests (`tests/test_config.py`)**
   - Save/load `ollama_api_key` and `ollama_base_url`.
   - Backward-compatible load for configs without new fields.
2. **Setup tests (`tests/test_setup_command.py`)**
   - Setup accepts and persists new Ollama options.
   - Provider-aware summary validation routes to Ollama for `ollama:` models.
   - Missing Ollama key errors are explicit.
3. **Adapter/client tests**
   - New `tests/test_ollama_client.py` validates request mapping and response extraction.
   - Runtime adapter selection tests verify prefix routing and model-name stripping.
4. **Regression safety**
   - Existing OpenAI/Gemini summary paths remain green with unchanged behavior.

## Documentation updates

1. README setup examples include `--ollama-api-key` and optional `--ollama-base-url`.
2. README config example includes `ollama_api_key` and `ollama_base_url`.
3. Document summary provider selection rule for `summary_model=ollama:<model-name>`.

## Acceptance criteria

1. User can configure `summary_model` as `ollama:<model-name>` and generate summaries/cards via Ollama Cloud.
2. OpenAI embeddings remain required and unchanged.
3. Setup/runtime errors clearly identify missing Ollama credentials or provider failures.
4. Existing OpenAI/Gemini workflows continue without regressions.
5. New and updated tests pass.
