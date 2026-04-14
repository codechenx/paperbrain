# Remove Old Heuristic Code Design

## Context

`paperbrain/adapters/llm.py` still contains legacy heuristic person/topic derivation code and a deterministic adapter path that are no longer part of the desired architecture. The target architecture is LLM-driven person/topic card generation.

## Goals

1. Remove old heuristic person/topic derivation helpers from `llm.py`.
2. Remove `DeterministicLLMAdapter` and test references to it.
3. Keep runtime summarize flow and `OpenAISummaryAdapter` contracts unchanged.

## Non-goals

1. Changing summarize-service orchestration.
2. Changing schema/validator rules for LLM-generated person/topic payloads.
3. Introducing new prompt or card fields.

## Approved design

### 1) Code removal

Delete these legacy items from `paperbrain/adapters/llm.py`:

1. `_infer_theme_from_text`
2. `_derive_person_cards`
3. `_derive_topic_cards`
4. `DeterministicLLMAdapter`

After removal, only the `OpenAISummaryAdapter` path remains for person/topic derivation.

### 2) Test updates

Update `tests/test_openai_adapter.py`:

1. Remove `DeterministicLLMAdapter` import and deterministic-adapter tests.
2. Keep and/or strengthen tests for `OpenAISummaryAdapter` prompt contracts and strict validation behavior.

### 3) Safety/validation

1. Preserve `OpenAISummaryAdapter.derive_person_cards` / `derive_topic_cards` public behavior.
2. Preserve existing retry-and-fail semantics for invalid LLM payloads.
3. Run targeted and full test suites to verify no regressions.

## Impacted files

1. `paperbrain/adapters/llm.py`
2. `tests/test_openai_adapter.py`
