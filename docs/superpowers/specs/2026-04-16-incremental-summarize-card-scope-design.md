# Incremental Summarize with Card Scope Design

## Problem statement

PaperBrain currently summarizes papers incrementally, but users need clearer control over update scope and better guarantees that incremental runs touch only related cards. The existing `--force-all` flag is also too coarse for selective rebuild workflows.

## Scope

In scope:
1. Replace `summarize --force-all` with `summarize --card-scope`.
2. Support `--card-scope` values: `all`, `paper`, `person`, `topic`.
3. Default `summarize` behavior (no `--card-scope`) should be incremental, updating only cards related to newly ingested papers.
4. `--card-scope` behavior should run full rebuild for the selected scope:
   - `all`: full rebuild for all card types
   - `paper`: full rebuild for all paper cards
   - `person`: full rebuild for all person cards
   - `topic`: full rebuild for all topic cards
5. Preserve relation integrity when recomputing related person/topic subsets in incremental mode.

Out of scope:
1. Changes to ingest dedupe semantics.
2. Changes to provider selection rules (`openai:`, `gemini:`, `ollama:`).
3. UI/web workflow changes.

## Approved approach

Implement scope-aware summarize orchestration with two execution paths:
1. **Default incremental path (no `--card-scope`)**:
   - summarize newly ingested papers only;
   - identify related people/topics through graph links;
   - regenerate only affected person/topic cards with full related context.
2. **Explicit rebuild path (`--card-scope ...`)**:
   - run full rebuild for the selected scope(s), replacing old `--force-all`.

Rationale:
1. Default path minimizes unnecessary recomputation.
2. Explicit scope option provides deterministic rebuild control.
3. Graph-based affected-set expansion avoids partial/stale relation updates.

## CLI contract

`paperbrain summarize [--card-scope <all|paper|person|topic>] [--config-path PATH]`

Behavior:
1. No `--card-scope`: incremental affected-only updates (all card types, but only related entities).
2. `--card-scope all`: full rebuild of paper/person/topic cards.
3. `--card-scope paper`: full rebuild of all paper cards only.
4. `--card-scope person`: full rebuild of all person cards only.
5. `--card-scope topic`: full rebuild of all topic cards only.

## Architecture/components

1. **`paperbrain/cli.py`**
   - Remove `--force-all` from `summarize`.
   - Add `--card-scope` option.
   - Pass scope mode to summarize service.
2. **`paperbrain/services/summarize.py`**
   - Add scope-aware run orchestration.
   - Separate default incremental graph update flow from explicit full-rebuild scope flows.
3. **`paperbrain/repositories/postgres.py`**
   - Add helper queries for affected-set expansion and context loading:
     - new paper selection for incremental,
     - person/topic graph traversal by link tables,
     - card fetch helpers by slug sets.
4. **Tests**
   - Update summarize service tests for scope contract and affected-only behavior.
   - Update CLI tests for new option and `--force-all` removal.
   - Add repository tests for new graph/helper query behavior.

## Incremental data flow (default run)

1. Fetch papers with no paper card (newly ingested set).
2. Generate/upsert paper cards for that new set only.
3. Build affected person set:
   - people linked to newly summarized papers,
   - plus newly derived person slugs from new paper cards.
4. Load full paper-card context for affected people and regenerate affected person cards.
5. Build affected topic set from topics linked to affected people.
6. Load full person-card context for affected topics (including connected people) and regenerate affected topic cards.
7. Upsert only affected person/topic outputs.

## Full rebuild data flow (`--card-scope`)

1. `all`:
   - rebuild all paper cards from all papers;
   - rebuild all person cards from all article paper cards;
   - rebuild all topic cards from all person cards.
2. `paper`:
   - rebuild all paper cards only.
3. `person`:
   - rebuild all person cards only from all article paper cards.
4. `topic`:
   - rebuild all topic cards only from all person cards.

## Error handling

1. Invalid `--card-scope` value must fail fast with clear allowed values.
2. Missing prerequisites for scoped rebuilds (for example, no source cards available) must return explicit zero-update outcomes, not silent fallbacks to other scopes.
3. Preserve existing explicit error handling for invalid card payload/link constraints.

## Testing strategy

1. Add targeted service tests for:
   - default incremental updating only related cards,
   - each scope value triggering expected full-rebuild scope behavior.
2. Add graph-integrity tests ensuring unaffected cards remain unchanged in incremental mode.
3. Add CLI contract tests:
   - `--card-scope` accepted values,
   - old `--force-all` removed/rejected.
4. Run full test suite after updates.

## Acceptance criteria

1. `summarize` no longer exposes `--force-all`.
2. `summarize --card-scope` supports `all|paper|person|topic` with approved semantics.
3. Default summarize run updates only cards related to newly ingested papers.
4. Scoped full rebuilds update only the intended scope(s).
5. Tests verify incremental relation integrity and scope-specific rebuild behavior.
