# Explicit Provider Prefix Selection Design

## Problem statement

PaperBrain currently mixes provider selection styles (`gemini-*`, `ollama:*`, and implicit OpenAI fallback). We need one consistent selector contract using explicit prefixes for all summary providers.

## Scope

In scope:
1. Require `summary_model` to use explicit provider prefixes:
   - `openai:<model>`
   - `gemini:<model>`
   - `ollama:<model>`
2. Remove implicit OpenAI fallback for unprefixed models.
3. Update runtime/setup routing, tests, and README examples to use explicit prefixes.

Out of scope:
1. Backward compatibility for old unprefixed or `gemini-*` selectors.
2. Automatic migration of existing config values.

## Approved approach

Adopt a strict, explicit prefix parser shared by runtime and setup routing.

Rationale:
1. Consistent and predictable provider selection behavior.
2. Eliminates ambiguity between model names and provider routing rules.
3. Keeps error handling straightforward: unprefixed/unknown selectors fail fast.

## Architecture/components

1. **`paperbrain/cli.py`**
   - Replace current Gemini/OpenAI fallback detection with explicit prefix checks:
     - `openai:`
     - `gemini:`
     - `ollama:`
   - Route summary adapters by parsed provider.
   - Strip prefix before passing model name to provider clients.
   - Raise clear `ValueError` when prefix is missing/unknown or model name is empty after prefix.
2. **`paperbrain/services/setup.py`**
   - Apply the same prefix-based routing for provider connection validation.
   - Validate selected provider credentials based on parsed prefix.
3. **`tests/test_setup_command.py` and related tests**
   - Update model samples to prefixed form:
     - `openai:gpt-4.1-mini`
     - `gemini:gemini-2.5-flash`
     - `ollama:gemma4` (or existing Ollama test models)
   - Add/adjust tests for invalid unprefixed/unknown selector errors.
4. **`README.md`**
   - Update setup examples and provider-selection rules to explicit prefix format.

## Data flow

1. User stores `summary_model` with explicit prefix in config.
2. Setup/runtime parse prefix and normalized model name.
3. Provider-specific key checks and summary client routing use parsed provider only.

## Error handling

1. Missing prefix fails fast with actionable error (must use `openai:`, `gemini:`, or `ollama:`).
2. Unknown prefix fails fast with actionable error.
3. Empty model name after valid prefix fails fast.

## Testing strategy

1. Update existing provider-routing tests to prefixed models.
2. Add coverage for invalid selector formats:
   - unprefixed (`gpt-4.1-mini`)
   - unknown prefix (`anthropic:claude-...`)
   - empty suffix (`openai:` / `gemini:` / `ollama:`)
3. Run full suite after updates.

## Documentation updates

1. README setup examples must use prefixed models.
2. Provider selection section documents explicit-prefix-only rule.

## Acceptance criteria

1. `summary_model` routes correctly only when prefixed with `openai:`, `gemini:`, or `ollama:`.
2. Unprefixed and unknown selectors are rejected with clear errors.
3. Tests and README reflect explicit-prefix-only behavior.
