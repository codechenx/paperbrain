# Commands

## Baseline checks

Run baseline tests before workflow commands:

```bash
python3 -m pytest -q
```

Confirm config and database connectivity are available for the active profile before ingest/summarize/export.

## Ingest command guidance

Use ingest on a single file or directory first, then scale up:

```bash
paperbrain ingest /path/to/pdfs --recursive
```

Use `--force-all` only when you intentionally need full re-processing.

## Summarize command guidance

Run summarize after ingest to generate or refresh cards:

```bash
paperbrain summarize
```

`--force-all` can be expensive and overwrite previous summaries; use it only for explicit full rebuilds.

## Export command guidance

Export after summarize and verify output structure:

```bash
paperbrain export --output-dir /path/to/exported_cards
```

Check that `index.md` plus `papers/`, `people/`, and `topics/` are created.
