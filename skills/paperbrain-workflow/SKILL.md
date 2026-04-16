---
name: paperbrain-workflow
description: Run and troubleshoot PaperBrain ingest/summarize/export workflows with validation and duplicate checks.
---

# PaperBrain Workflow

Use this skill to run PaperBrain workflows safely, diagnose provider/auth issues, and verify export output before reporting completion.

## When to use this skill

- You are asked to run ingest, summarize, or export.
- A workflow run failed and needs triage.
- You need a repeatable completion report with evidence.

Read `references/commands.md` before running workflow commands.
If provider auth fails, read `references/provider-troubleshooting.md`.
If duplicate exports are suspected, read `references/dedupe-and-export-checks.md`.

## Workflow checklist

1. Confirm environment and baseline checks from `references/commands.md`.
2. Select summary provider using explicit prefixes only:
   - `openai:<model>`
   - `gemini:<model>`
   - `ollama:<model>`
3. Run ingest for target files/directories.
4. Run summarize and confirm card generation signals.
5. Run export and inspect output structure.
6. If issues appear, follow the matching reference guide and re-run minimally.

## Validation loop

1. Capture command, return code, and key stdout/stderr evidence.
2. Validate expected artifacts (records/cards/files) for the step that just ran.
3. If validation fails, apply targeted fixes and rerun only the failed stage.
4. Re-check duplicates and export integrity before moving forward.
5. Repeat until all stages are validated.

## Completion gate

Do not mark the workflow complete until all fields are reported:

- `provider_model`: exact prefixed model value used.
- `baseline_checks`: what passed before workflow execution.
- `ingest_result`: scope, command, and outcome.
- `summarize_result`: command, outcome, and card/update evidence.
- `export_result`: output path and file-layout evidence.
- `validation_findings`: duplicate/export/provider checks performed.
- `follow_up`: remaining risks or `none`.
