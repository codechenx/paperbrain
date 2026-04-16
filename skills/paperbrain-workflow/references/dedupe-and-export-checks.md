# Dedupe and Export Checks

## Duplicate diagnostics

When duplicates are suspected, inspect repeated inputs and derived card collisions:

- Check repeated ingest targets and overlapping recursive paths.
- Verify whether multiple records point at the same `source_path`.
- Compare generated slugs for papers/people/topics to detect collisions.

If duplicate records are found, clean up the bad subset and rerun only the required stage.

## Export diagnostics

Validate export output after summarize:

- Ensure `index.md` exists and links resolve.
- Confirm `papers/`, `people/`, and `topics/` directories are populated.
- Spot-check a few files for missing sections, broken wikilinks, or repeated content.
- If exports look stale, rerun summarize first, then export again.
