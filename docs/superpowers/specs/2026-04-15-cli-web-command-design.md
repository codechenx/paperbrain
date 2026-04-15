# CLI `paperbrain web` Command Design

## Problem statement

PaperBrain already has a FastAPI web app (`paperbrain.web.app`) but no first-class CLI command to run it. Users currently need to know internal module paths and invoke `uvicorn` manually.

## Scope

In scope:
1. Add `paperbrain web` command to start the FastAPI app.
2. Expose runtime options: `--host`, `--port`, `--reload`, `--config-path`.
3. Default values:
   - `--host`: `127.0.0.1`
   - `--port`: `8000`
   - `--reload`: off
   - `--config-path`: `./config/paperbrain.conf`
4. Add CLI tests for help visibility and uvicorn wiring.

Out of scope:
1. Changing web routes/templates/repository behavior.
2. Background daemonization or process supervision.
3. Auto-opening browser tabs.

## Approved approach

Use a direct Typer command that calls `uvicorn.run` in-process.

Why:
1. Smallest change, consistent with current Typer command style.
2. Avoids subprocess shelling and path fragility.
3. Easy to test by monkeypatching `uvicorn.run`.

## Architecture/components

1. **`paperbrain/cli.py`**
   - Add `web` command.
   - Import `uvicorn`.
   - Print startup URL.
   - Build an app-factory closure that calls `create_app(config_path=...)`.
   - Call `uvicorn.run(app_factory, factory=True, host=..., port=..., reload=...)`.
2. **`tests/test_cli_commands.py`**
   - Ensure `web` appears in `--help`.
3. **New/updated CLI command tests**
   - Verify defaults and explicit options are forwarded to `uvicorn.run`.
   - Verify `config_path` is passed to app factory kwargs.

## Data flow

1. User runs: `paperbrain web [options]`.
2. Typer parses options and resolves default values.
3. Command builds app-factory closure using selected `config_path`.
4. Command invokes `uvicorn.run` with that closure.
5. Uvicorn builds app via `create_app(config_path=...)`.
6. Existing web app loads DB URL from selected config path and serves requests.

## Error handling

1. No new fallback layers.
2. Invalid config path or config contents surface through existing config/loading errors.
3. Uvicorn startup/runtime errors are surfaced directly.

## Testing strategy

1. Update help test to include `web`.
2. Add command test with monkeypatched `uvicorn.run` to assert:
   - default host `127.0.0.1`
   - default port `8000`
   - default reload `False`
   - forwarded config path
3. Add explicit-option test to assert non-default values are forwarded.

## Acceptance criteria

1. `paperbrain --help` lists `web`.
2. `paperbrain web` starts the FastAPI server with defaults (`127.0.0.1:8000`, reload off).
3. `paperbrain web --host ... --port ... --reload --config-path ...` forwards all values correctly.
4. Existing tests continue to pass.
