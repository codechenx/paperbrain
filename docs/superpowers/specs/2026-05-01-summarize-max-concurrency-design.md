# Summarize max-concurrency design

## Problem

The current `--limit` behavior truncates how many papers are processed in a run. The intended control is request pressure, not total work completed.

## Goal

Replace truncation semantics with concurrency semantics:

- Process all eligible papers in a summarize run.
- Use a new `--max-concurrency` option to cap simultaneous LLM requests.
- Remove `--limit` entirely (no backward compatibility).

## Scope

In scope:

- CLI option replacement (`--limit` -> `--max-concurrency`)
- Summarize service API update (`limit` -> `max_concurrency`)
- Paper summarization implementation changed to bounded concurrency
- Test updates for new contract and removed legacy flag

Out of scope:

- Provider/model selection behavior
- Schema changes
- Reintroducing `summary` alias

## Design

### CLI contract

- `summarize` accepts `--max-concurrency` as an integer option.
- Default value is `1` (safe, serialized behavior).
- `--limit` is removed; invoking it should fail as unknown option.

### Service contract

- `SummarizeService.run(..., max_concurrency=1)` replaces `limit`.
- Paper stage processes the full `list_papers_for_summary(...)` result set.
- Request parallelism is bounded by `max_concurrency`.
- Existing stage sequencing remains:
  - default/all run papers first
  - downstream person/topic only run once paper completion gate allows

### Concurrency behavior

- Use bounded worker execution (thread pool or equivalent) for LLM paper summarization calls.
- Preserve deterministic DB upsert behavior: every successful paper summary is upserted once.
- If one paper fails, propagate error consistently with current failure model (no silent drops).

### Validation

- Reject non-positive `--max-concurrency` values at CLI boundary with clear parameter error.

## Testing strategy

1. CLI tests:
   - `--max-concurrency` is passed to `SummarizeService.run`.
   - `--limit` is rejected.
2. Service tests:
   - all eligible papers are processed in a run (no truncation).
   - bounded concurrency path still returns correct counts.
3. Regression:
   - staged sequencing tests remain green.
   - full test suite remains green.

## Risks and mitigations

- Risk: race issues around shared resources during parallel summarization.
  - Mitigation: keep per-paper work isolated; centralize only upsert call boundaries.
- Risk: request spikes if misconfigured.
  - Mitigation: default `max_concurrency=1` and CLI validation.
