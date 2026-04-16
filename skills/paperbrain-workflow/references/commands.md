# Commands

## Baseline checks

Run baseline tests before workflow commands:

```bash
python3 -m pytest -q
```

Use an explicit config path for every command:

```bash
CONFIG_PATH="/abs/path/to/config.toml"
```

Confirm config and database connectivity are available for the active profile before ingest/summarize/export:

```bash
paperbrain stats --config-path "$CONFIG_PATH"
```

## Canonical ingest pattern

Run ingest on a single file or directory first, then scale up:

```bash
paperbrain ingest /abs/path/to/pdfs --recursive --config-path "$CONFIG_PATH"
```

Post-ingest verification commands:

```bash
paperbrain stats --config-path "$CONFIG_PATH"
paperbrain search "<title keyword>" --top-k 3 --include-cards --config-path "$CONFIG_PATH"
```

Use `--force-all` only when you intentionally need full re-processing.

## Canonical summarize pattern

Run summarize after ingest to generate or refresh cards:

```bash
paperbrain summarize --config-path "$CONFIG_PATH"
```

Post-summarize verification commands:

```bash
paperbrain search "<title keyword>" --top-k 3 --include-cards --config-path "$CONFIG_PATH"
paperbrain stats --config-path "$CONFIG_PATH"
```

`--force-all` can be expensive and overwrite previous summaries; use it only for explicit full rebuilds.

## Canonical export pattern

Export after summarize and verify output structure:

```bash
paperbrain export --output-dir /abs/path/to/export --config-path "$CONFIG_PATH"
```

Post-export verification commands:

```bash
test -f /abs/path/to/export/index.md
find /abs/path/to/export -maxdepth 2 -type d | sort
```

Check that `index.md` plus `papers/`, `people/`, and `topics/` are created.
