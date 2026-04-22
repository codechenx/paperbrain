# Summarize staged sequencing design

## Problem

Incremental summarize currently derives person/topic cards while paper-card generation is still in progress, which causes repeated downstream LLM work and higher request usage.

## Goal

Enforce stage ordering so downstream derivations only run after upstream datasets are complete:

1. Paper cards first
2. Person cards after all paper cards are generated
3. Topic cards after person cards are generated

Applies to default `summarize` flow and `--card-scope all`.

## Non-goals

- No output format changes
- No change to explicit `--card-scope person` and `--card-scope topic` behavior
- No schema changes

## Design

### Command behavior

- `summarize` (default flow) and `summarize --card-scope all` run staged logic.
- Stage 1 summarizes paper cards (respecting `--limit`).
- After Stage 1, service checks whether unsummarized papers remain.
  - If yes: stop and return counts for papers only (`person_cards=0`, `topic_cards=0`).
  - If no: continue to person/topic stages.

### Downstream stages after paper completion

- Person stage derives person cards from all article paper cards and upserts.
- Topic stage derives topic cards from all person cards and upserts.
- Topic stage always executes after person stage in the same run once paper completion gate passes.

### Explicit scope behavior

- `--card-scope paper`: unchanged except for existing limit behavior.
- `--card-scope person`: unchanged, runs person derivation directly.
- `--card-scope topic`: unchanged, runs topic derivation directly.

## Error handling

- Preserve existing invalid `card_scope` validation.
- Preserve existing empty-input short-circuit behavior in person/topic derivation paths.
- No silent swallowing of derivation errors; keep current exception behavior.

## Testing

Add/adjust tests to prove staged gating:

1. Default flow skips person/topic while unsummarized papers remain.
2. `--card-scope all` skips person/topic while unsummarized papers remain.
3. Default/all run person then topic only after paper completion condition is met.
4. Existing explicit person/topic scope tests remain valid.

