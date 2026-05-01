# CLI backward-compat cleanup design

## Problem

The CLI has accumulated compatibility-oriented command/flag paths and tests around legacy behavior. This increases maintenance cost and can obscure the canonical contract.

## Goal

Perform a contract-first CLI cleanup:

- Keep only canonical commands/options.
- Remove legacy/backward-compat CLI surfaces immediately (no deprecation period).
- Keep runtime feature behavior unchanged aside from removed compatibility entry points.

## Scope

In scope:

- `paperbrain/cli.py` command/option compatibility surfaces.
- CLI-facing docs and examples.
- CLI tests that currently preserve or assert backward-compat pathways.

Out of scope:

- Non-CLI internal refactors.
- Database schema or data model changes.
- Provider/model behavior changes.

## Design

### Architecture and boundaries

- Treat CLI as strict public contract.
- Keep one canonical command/flag per behavior.
- Remove aliases/shims/legacy flags from CLI wiring.
- Ensure tests fail fast on removed compatibility paths (`No such command/option`).

### Implementation surfaces

1. Inventory all compatibility-oriented CLI paths in `paperbrain/cli.py`.
2. Remove legacy command aliases and option shims.
3. Update CLI docs/examples to only canonical syntax.
4. Update tests to assert removed compatibility surfaces are rejected.

### Error handling

- Preserve existing Typer validation for supported options.
- Use Typer default unknown command/option errors for removed legacy paths.
- Do not add silent fallback routing.

## Testing strategy

1. Targeted CLI contract tests (setup/summarize/ingest related flags and commands).
2. Add or update explicit rejection tests for removed legacy entries.
3. Full suite run to confirm no regressions.

## Migration policy

- Immediate removal approved by user.
- No backward-compat grace period.
