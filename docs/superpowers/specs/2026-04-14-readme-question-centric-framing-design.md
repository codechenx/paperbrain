# README Question-Centric Framing Design

## Problem statement

The README currently explains infrastructure and workflow clearly, but it under-emphasizes PaperBrain's core identity: a **card-system design** for **scientific-question-centric paper digesting**.

Readers should quickly understand that PaperBrain is not only a PDF-to-database pipeline; it is a research-question synthesis system built around paper/person/topic cards.

## Scope

In scope:
1. README messaging updates only.
2. Add a short “Core Concept” section near the top.
3. Adjust nearby wording to align workflow and card descriptions with question-centric framing.

Out of scope:
1. CLI, schema, adapter, or service behavior changes.
2. Command syntax or operational workflow changes.
3. New diagrams or major structural rewrite of the entire README.

## Approved design

### 1. Content architecture

1. Keep existing README structure largely intact.
2. Add a concise top-level “Core Concept” section after the project intro.
3. Reframe adjacent sections so card-system intent appears before implementation details.

### 2. Data-flow/message alignment

1. Preserve existing ASCII flow shape and command references.
2. Update wording to emphasize:
   - question-centered paper cards as the primary digest unit,
   - person cards as long-horizon big-question synthesis,
   - topic cards as grouped cross-person question themes.
3. Keep installation/usage references unchanged except for phrasing consistency.

### 3. Boundaries and consistency

1. Documentation-only update; no code changes.
2. Ensure consistent terminology:
   - “card system”
   - “scientific question-centric digest”
   - “paper/person/topic question synthesis”
3. Remove conflicting infrastructure-first phrasing where it undermines the core concept.

## Acceptance criteria

1. README opening clearly states PaperBrain’s key concept as a card-system design for scientific question-centric digesting.
2. Workflow framing in early sections reflects question-centric card generation as the primary outcome.
3. Existing operational instructions remain accurate and usable.
