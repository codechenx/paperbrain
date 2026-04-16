# Dedupe and Export Checks

## Duplicate diagnostics

When duplicates are suspected, inspect repeated inputs and derived card collisions:

- Check repeated ingest targets and overlapping recursive paths.
- Verify whether multiple records point at the same `source_path`.
- Compare generated slugs for papers/people/topics to detect collisions.

### `source_path` mismatch check (absolute vs relative)

If two records look duplicated but `source_path` values differ, run this check flow:

1. Pair the suspect records and compare their file names + slugs first.
2. Inspect path style:
   - Absolute path example: `/home/user/library/papers/foo.pdf`
   - Relative path example: `papers/foo.pdf`
3. Normalize both paths to the same base directory and compare the resolved result.
4. If normalized paths match, treat this as a path-format mismatch (not distinct sources), dedupe the extra record, and rerun summarize/export.
5. If normalized paths differ, keep both and continue duplicate diagnostics.

If duplicate records are found, clean up the bad subset and rerun only the required stage.

## Export diagnostics

Validate export output after summarize:

- Ensure `index.md` exists and links resolve.
- Confirm `papers/`, `people/`, and `topics/` directories are populated.
- Spot-check a few files for missing sections, broken wikilinks, or repeated content.
- If exports look stale, rerun summarize first, then export again.
