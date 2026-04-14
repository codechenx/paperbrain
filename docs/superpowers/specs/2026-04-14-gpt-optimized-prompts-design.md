# GPT-Optimized Prompt Redesign for `llm.py`

## Context

Current prompts in `paperbrain/adapters/llm.py` are functional but too terse. The requested change is to make prompts significantly more explicit and GPT-optimized while preserving current strict output contracts and validators.

## Goals

1. Rewrite **all** prompt blocks in `llm.py` with clearer, more detailed instruction structure.
2. Use role-specific framing:
   - **Paper summary:** senior reviewer persona.
   - **Person/topic generation:** senior professor persona.
3. Add rubric-style guidance where relevant (especially paper, person, topic prompts).
4. Preserve output schemas and downstream behavior (no contract drift).

## Non-goals

1. Changing persistence schema or card model fields.
2. Relaxing strict JSON or validator rules.
3. Changing summarize-service flow or retry policy.

## Prompt Architecture Standard

Every rewritten prompt follows this block order:

1. **Role and objective**
2. **Evidence boundary** (“use only provided text/input”; no external facts)
3. **Task rubric/checklist**
4. **Output schema contract** (strict JSON shape)
5. **Failure/default rules** (unknown values policy)

## Prompt-by-Prompt Design

### 1) Bibliographic metadata prompt (`_infer_bibliographic_fields`)

Design:
- Keep extraction limited to first-page OCR/text.
- Add explicit extraction policy:
  - authors = people listed as authors only,
  - journal = publication venue string,
  - year = publication year integer.
- Add ambiguity handling:
  - unknown authors => `[]`
  - unknown journal => `""`
  - unknown year => `0`
- Output must remain strict JSON object with keys `authors`, `journal`, `year`.

### 2) Paper summary prompt (`_build_summary`)

Role framing (required):
- “You are a senior reviewer of a famous scientific journal. You always evaluate the innovation and logic of scientific papers.”

Design:
- Explicitly state: summarize using only provided text.
- Add rubric bullets:
  - novelty/innovation claim quality,
  - logical flow of claims and experiments,
  - method-to-result coherence,
  - figure-grounded evidence quality,
  - limitation realism and scope.
- Preserve dual-mode schema:
  - article keys: `key_question_solved`, `why_important`, `method`, `findings_logical_flow`, `key_results_with_figures`, `limitations`, `paper_type`.
  - review keys: `key_goal`, `unsolved_questions`, `why_important`, `why_unsolved`, `paper_type`.
- Keep strict JSON-only response requirement.

### 3) Corresponding-author prompt (`_infer_corresponding_authors` fallback)

Design:
- Keep extraction from first-page text only.
- Add explicit rule: return only valid email addresses.
- Add strict output requirement: JSON array only, no prose.
- Keep existing post-parse normalization and dedupe behavior unchanged.

### 4) Person-generation prompt (`_generate_person_big_questions`)

Role framing:
- Senior professor persona focused on long-horizon research direction quality.

Design:
- Add rubric for each big question:
  - concrete scientific question wording,
  - strategic importance,
  - explicit grounding in linked papers only,
  - no fabricated papers or unsupported claims.
- Preserve strict contract:
  - `focus_area` must be exactly `[]`,
  - non-empty `big_questions`,
  - each entry includes `question`, `why_important`, `related_papers` subset of linked papers.
- Keep retry-once then fail behavior unchanged.

### 5) Topic-generation prompt (`_build_topic_prompt`)

Role framing:
- Senior professor persona focused on theme synthesis across researchers.

Design:
- Add rubric:
  - themes must emerge from provided big questions,
  - grouping should maximize conceptual coherence,
  - maintain traceable people/paper links for each grouped question.
- Preserve strict contract:
  - topic card keys unchanged,
  - `related_big_questions` must map to input questions,
  - people/paper references must come only from input.
- Keep retry-once + strict validation behavior unchanged.

## Testing Impact

Update prompt-focused tests in `tests/test_openai_adapter.py` to assert:

1. Persona language is present in relevant prompts.
2. Rubric/checklist language is present for paper/person/topic prompts.
3. Strict JSON-only response requirements remain explicit.
4. Existing contract/validation tests remain green.

## Implementation Notes

1. Keep modifications localized to prompt string builders/call sites in `paperbrain/adapters/llm.py`.
2. Avoid changing validator logic unless required by test brittleness.
3. Keep deterministic adapter behavior unchanged in this prompt pass.
