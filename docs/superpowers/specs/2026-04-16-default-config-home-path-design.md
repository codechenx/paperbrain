# Default Config Path to Home Directory Design

## Problem statement

PaperBrain currently defaults to `./config/paperbrain.conf`. We need the default configuration path to be the user-scoped location `~/.config/paperbrain/paperbrain.conf`.

## Scope

In scope:
1. Change CLI default config path constant to `~/.config/paperbrain/paperbrain.conf`.
2. Keep `--config-path` override behavior unchanged.
3. Update tests and README to match the new default.

Out of scope:
1. New environment-variable config path selectors.
2. New config migration logic.

## Approved approach

Use a single canonical default path constant in `paperbrain/cli.py` based on `Path.home()`, and align tests/docs to that constant behavior.

Rationale:
1. Minimal, low-risk change.
2. Keeps existing override interfaces unchanged.
3. Ensures CLI and web path defaults stay consistent because web imports `DEFAULT_CONFIG_PATH`.

## Design details

1. **Code**
   - In `paperbrain/cli.py`, set:
     - `DEFAULT_CONFIG_PATH = Path.home() / ".config" / "paperbrain" / "paperbrain.conf"`.
   - Keep all `--config-path` options unchanged.
2. **Tests**
   - Update tests that assert `Path("config/paperbrain.conf")` to assert the new home-based default.
3. **Docs**
   - Update README default config path text to `~/.config/paperbrain/paperbrain.conf`.

## Error handling and compatibility

1. No behavior change for users already passing `--config-path`.
2. Setup still creates parent directories via existing `ConfigStore.save` behavior.

## Testing strategy

1. Run baseline full suite before edits.
2. Run full suite after edits to verify no regressions.

## Acceptance criteria

1. Running commands without `--config-path` uses `~/.config/paperbrain/paperbrain.conf` by default.
2. README and tests reflect the new default path.
3. Full test suite passes.
