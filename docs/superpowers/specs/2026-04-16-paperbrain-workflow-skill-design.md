# PaperBrain Workflow Skill Design

## Problem statement

We need a reusable Agent Skill that reliably runs PaperBrain’s ingest/summarize/export workflow with consistent validation, failure handling, and duplicate checks. Current execution knowledge is spread across ad hoc session history and troubleshooting conversations.

## Scope

In scope:
1. Define one shared skill under `skills/paperbrain-workflow/` for project-specific workflow guidance.
2. Cover end-to-end flow: config validation, ingest, summarize, export, and post-run verification.
3. Add progressive-disclosure references for commands, provider troubleshooting, and duplicate/export diagnostics.
4. Standardize run-summary output format (counts, skips, failure categories, next actions).

Out of scope:
1. Splitting into multiple agent-specific skill variants.
2. Implementing new PaperBrain product features.
3. Replacing project tests or CI configuration.

## Approved approach

Create a single moderate-detail skill with:
1. A concise `SKILL.md` that contains only high-value operational rules, checklists, and gotchas.
2. Targeted `references/` files loaded only when specific triggers occur.
3. A strict validation loop for workflow completion and explicit failure reporting.

Rationale:
1. Keeps context cost low while preserving operational reliability.
2. Encodes project-specific behavior the base model is likely to miss.
3. Reduces repeated debugging effort for known failure modes.

## Architecture/components

1. **`skills/paperbrain-workflow/SKILL.md`**
   - Frontmatter:
     - `name: paperbrain-workflow`
     - `description: Run and troubleshoot PaperBrain ingest/summarize/export workflows with validation and duplicate checks.`
   - Core content:
     - When to use.
     - Mandatory execution checklist.
     - Provider/model selector requirements (`openai:`, `gemini:`, `ollama:`).
     - Validation loop and completion gate.
     - Triggered reference-loading instructions.
2. **`skills/paperbrain-workflow/references/commands.md`**
   - Canonical command patterns (config path, ingest targets, summarize/export runs, targeted verification commands).
3. **`skills/paperbrain-workflow/references/provider-troubleshooting.md`**
   - Auth/provider failure diagnosis map and next-command actions.
4. **`skills/paperbrain-workflow/references/dedupe-and-export-checks.md`**
   - Duplicate-card diagnostics, path-style mismatch checks, and remediation guidance.

## Workflow/data flow

1. Validate configuration location and required provider credentials.
2. Ingest PDFs with explicit path handling and `--force-all` semantics.
3. Summarize using explicit provider-prefixed model selectors.
4. Export cards to target directory.
5. Run post-run validation:
   - count reconciliation (ingested/summarized/exported),
   - skipped categories,
   - duplicate/export sanity checks.
6. Emit standardized summary output and next actions when any check fails.

## Error handling strategy

1. No silent fallbacks for provider or model-selection errors.
2. For each failure category, emit:
   - observed symptom,
   - likely cause,
   - one concrete next diagnostic command.
3. Load troubleshooting references only on matching triggers to avoid unnecessary context bloat.

## Testing strategy

1. Validate the skill by executing representative workflow scenarios:
   - normal run with configured provider,
   - missing credential scenario,
   - duplicate-export diagnostic scenario.
2. Confirm generated run summaries include required fields and actionable failure guidance.
3. Ensure instructions stay consistent with current repository commands and config defaults.

## Acceptance criteria

1. Skill exists at `skills/paperbrain-workflow/` with required `SKILL.md` metadata and structured instructions.
2. Workflow checklist enforces ingest/summarize/export plus post-run validation.
3. References are explicitly trigger-driven and cover commands, provider troubleshooting, and dedupe/export checks.
4. Skill guidance requires explicit prefixed summary model selectors and explicit failure reporting.
5. A user can run the workflow end-to-end with consistent output format and clear next actions on failure.
