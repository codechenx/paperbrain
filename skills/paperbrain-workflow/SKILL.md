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
- `counts`: key totals from run output (for example, ingested papers, summarized cards, exported files).
- `skipped_categories`: categories skipped during the run and why, or `none`.
- `failure_categories`: any failure buckets encountered (auth, quota, model, export, etc.) and current status, or `none`.
- `failure_details`: for each item in `failure_categories`, include `symptom`, `likely_cause`, and `diagnostic_command` (plus current remediation status).
- `validation_findings`: duplicate/export/provider checks performed.
- `next_actions`: explicit next actions to complete remediation or `none`.

### Scenario run-summary template

```json
{
  "provider_model": "ollama:llama3.1",
  "baseline_checks": "python3 -m pytest -q passed; paperbrain stats --config-path \"$CONFIG_PATH\" passed",
  "ingest_result": {
    "scope": "42 PDFs under /data/papers",
    "command": "paperbrain ingest /data/papers --recursive --config-path \"$CONFIG_PATH\"",
    "outcome": "success (42 records ingested)"
  },
  "summarize_result": {
    "command": "paperbrain summarize --config-path \"$CONFIG_PATH\"",
    "outcome": "partial_success (2 auth failures)",
    "evidence": "40 cards updated, 2 failures in auth bucket"
  },
  "export_result": {
    "output_path": "/exports/paperbrain-run-2026-01-13",
    "file_layout_evidence": "index.md + papers/ + people/ + topics/ verified"
  },
  "counts": {
    "ingested_papers": 42,
    "summarized_cards": 40,
    "exported_files": 163
  },
  "skipped_categories": "none",
  "failure_categories": [
    "auth"
  ],
  "failure_details": [
    {
      "symptom": "401 Unauthorized on ollama:llama3.1",
      "likely_cause": "missing ollama_api_key in config",
      "diagnostic_command": "paperbrain summarize --config-path \"$CONFIG_PATH\"",
      "remediation_status": "updated config and rerun pending"
    }
  ],
  "validation_findings": "checked provider config keys, duplicate source_path mismatches, and export layout integrity",
  "next_actions": "rerun summarize after credential update, then rerun export"
}
```
