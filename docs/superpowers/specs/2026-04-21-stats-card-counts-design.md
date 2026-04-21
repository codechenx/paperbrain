# Stats Command Card Counts Design

## Problem

`paperbrain stats` currently reports `papers`, `authors`, and `topics`.  
The requested behavior is to report paper count plus card counts by card type, and to stop reporting `authors` and `topics`.

## Goals

1. Update `paperbrain stats` output to include:
   - `papers`
   - `paper_cards`
   - `person_cards`
   - `topic_cards`
2. Remove `authors` and `topics` from the stats output contract.
3. Keep command name and CLI options unchanged.
4. Implement via service/repository layer extension (not CLI-only SQL).

## Non-Goals

1. No new CLI command (such as `card-stats`).
2. No new CLI flags for stats output selection.
3. No schema changes.

## Design

### 1) Data model update

Update `CorpusStats` in `paperbrain/services/stats.py`:

- Keep: `papers`
- Remove: `authors`, `topics`
- Add: `paper_cards`, `person_cards`, `topic_cards`

### 2) Repository contract update

Update `StatsRepository` protocol and `DatabaseStatsRepository` implementation:

- Keep `count_papers()`
- Remove `count_authors()` and `count_topics()` from stats command path
- Add:
  - `count_paper_cards()` -> `SELECT COUNT(*) FROM paper_cards;`
  - `count_person_cards()` -> `SELECT COUNT(*) FROM person_cards;`
  - `count_topic_cards()` -> `SELECT COUNT(*) FROM topic_cards;`

### 3) Service mapping update

Update `StatsService.collect()` to populate the new `CorpusStats` fields using the new repository methods.

### 4) CLI output update

Update `paperbrain/cli.py` stats command output string to:

`Corpus stats: papers={papers} paper_cards={paper_cards} person_cards={person_cards} topic_cards={topic_cards}`

No command/flag changes.

## Error Handling

No new error behavior is introduced. Existing connection and SQL failure behavior remains unchanged.

## Testing Strategy

1. Update stats service/repository unit tests to assert the new fields and counts.
2. Update CLI stats output test(s) to match the new format.
3. Ensure removed `authors/topics` expectations are eliminated from stats-related tests.

## Compatibility Impact

This is an intentional output contract change for `paperbrain stats`.  
Any scripts parsing old `authors` or `topics` keys from the stats output must be updated to the new fields.
