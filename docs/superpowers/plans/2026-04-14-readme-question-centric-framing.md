# README Question-Centric Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update README messaging so PaperBrain is clearly presented as a card-system design for scientific-question-centric paper digesting.

**Architecture:** Keep the README structure and operational instructions intact while adding a top-level Core Concept section and rephrasing early workflow/data-flow/card-design text to be question-centric. Limit edits to `README.md` only and avoid code or command-syntax changes.

**Tech Stack:** Markdown, README content architecture, PaperBrain CLI docs

---

## File structure map

- **Modify:** `README.md:3-120`
  - Add core-concept framing and align early sections with question-centric card-system messaging.
- **No code/test files changed**

### Task 1: Add failing doc-contract checks (red phase)

**Files:**
- Modify: `README.md:3-120` (no edits yet; baseline check only)
- Test: command-line content checks against `README.md`

- [ ] **Step 1: Run baseline checks that should fail before edits**

Run:
```bash
cd /home/nous/projects/paperbrain
rg -n "Core Concept|scientific question-centric|card-system design|question-centered paper cards" README.md
```

Expected:
- Either no matches or incomplete matches for the full target framing phrases.
- This establishes a red baseline before content edits.

- [ ] **Step 2: Commit plan-owned baseline checkpoint note (no file changes expected)**

If no files changed, skip commit for this step and proceed to Task 2.

### Task 2: Implement README framing updates

**Files:**
- Modify: `README.md:3-120`
- Test: command-line content checks against `README.md`

- [ ] **Step 1: Add “Core Concept” section after intro**

Insert a new section near the top:

```markdown
## Core Concept

PaperBrain is a **card-system design** for a **scientific question-centric paper digest**.
It organizes evidence from papers into linked cards that prioritize research questions:
- **Paper cards** capture the key question, reasoning flow, evidence, and limitations.
- **Person cards** synthesize long-horizon big questions from linked papers.
- **Topic cards** group big questions into coherent cross-person research themes.
```

- [ ] **Step 2: Reframe “What PaperBrain does” into question-centric outcomes**

Update the workflow list language so it emphasizes question synthesis:

```markdown
## 1. What PaperBrain does

PaperBrain focuses on this question-centric workflow:
1. Ingest PDFs and extract clean evidence text
2. Build embeddings to support retrieval of question-relevant context
3. Generate structured **paper/person/topic** cards centered on scientific questions
4. Link cards bidirectionally across evidence, people, and themes
5. Export the card graph as markdown notes
```

- [ ] **Step 3: Reword early data-flow/card-design lines to match the core concept**

Adjust wording in the existing ASCII/data-flow and card-design descriptions, keeping the structure and commands unchanged. Update lines similar to:

```text
OpenAI summarization + deterministic post-processing
```

to question-centric framing such as:

```text
OpenAI summarization for question-centric card synthesis
```

and ensure card bullets consistently emphasize question-driven digesting.

- [ ] **Step 4: Run focused README contract checks**

Run:
```bash
cd /home/nous/projects/paperbrain
rg -n "Core Concept|scientific question-centric|card-system design|question-centered paper cards|question-centric workflow" README.md
```

Expected:
- Matches present for all required framing terms in README top sections.

- [ ] **Step 5: Commit README update**

```bash
cd /home/nous/projects/paperbrain
git add README.md
git commit -m "docs: reframe readme around question-centric card system" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Validate no operational-doc regressions

**Files:**
- Modify: `README.md` (only if wording fixes are needed)
- Test: `README.md` commands/sections remain intact

- [ ] **Step 1: Verify command reference rows still exist and are unchanged in meaning**

Run:
```bash
cd /home/nous/projects/paperbrain
rg -n "paperbrain setup|paperbrain init|paperbrain ingest|paperbrain summarize|paperbrain export" README.md
```

Expected:
- All command reference entries still present.

- [ ] **Step 2: Verify installation/config snippets still exist**

Run:
```bash
cd /home/nous/projects/paperbrain
rg -n "python3 -m pip install -e \\.|paperbrain setup|paperbrain init --url|config/paperbrain.conf" README.md
```

Expected:
- Installation/config instructions still present and readable.

- [ ] **Step 3: Commit any final wording-only fixes (if needed)**

```bash
cd /home/nous/projects/paperbrain
git add README.md
git commit -m "docs: finalize readme question-centric messaging consistency" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
