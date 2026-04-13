# Card Format and Author Inference Design

## Problem

Exported cards currently include summary marker comments and do not always follow `Design.md` section titles/structure. In addition, person/topic cards were missing because `corresponding_authors` was empty for ingested papers and derivation depended on that field.

## Approved Behavior

1. Remove all marker comments like `<!-- paperbrain_paper_summary:start/end -->` from exports.
2. Render paper/person/topic cards using `Design.md` section titles and structure.
3. During `summarize`, if `corresponding_authors` is missing, infer it via OpenAI from paper text/title.
4. Use inferred corresponding authors for person/topic derivation.
5. Add `index.md` in export output, grouped by Papers / People / Topics.

## Data Flow Changes

1. Summarization produces paper card body in `Design.md` format.
2. If `corresponding_authors` is empty, run a targeted inference prompt and fill the field.
3. Person cards derive from populated corresponding authors.
4. Topic cards derive from person-card question themes and preserve related links.
5. Export writes normalized markdown cards and an `index.md`.

## Error Handling

- If corresponding-author inference fails for a paper, report warning with the affected paper slug.
- Continue export/summarize for remaining papers.

## Tests

- Export tests for:
  - no marker comments
  - `Design.md` section titles in paper/person/topic markdown
  - `index.md` generation and grouped links
- Summarize tests for:
  - fallback corresponding-author inference when metadata is empty
  - downstream person/topic card generation from inferred data

