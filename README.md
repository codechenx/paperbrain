# PaperBrain

PaperBrain is a Python CLI for building a local scientific knowledge base from PDFs.
It uses:
- **PostgreSQL + pgvector** for storage and hybrid retrieval
- **Docling** for PDF parsing/OCR
- **OpenAI** for embeddings and card generation
- **Markdown export** for Obsidian-style linked notes

---

## 1. What PaperBrain does

PaperBrain focuses on this workflow:
1. Ingest PDFs and extract metadata/text
2. Build chunk embeddings for hybrid retrieval
3. Generate structured **paper/person/topic** cards
4. Link cards bidirectionally
5. Export everything as markdown files

---

## 2. Data flow (ASCII, with card design detail)

```text
┌──────────────────────────────┐
│ Local PDFs (single file/dir) │
└──────────────┬───────────────┘
               │ paperbrain ingest [--recursive] [--force-all]
               ▼
      ┌─────────────────────────────┐
      │ DoclingParser                │
      │ - full text                  │
      │ - first-page metadata clues  │
      │   (authors/journal/year/CA)  │
      └──────────────┬───────────────┘
                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL                                                               │
│  papers                  paper_chunks            paper_embeddings         │
│  - title/journal/year    - chunk_text            - vector(1536)          │
│  - authors               - chunk_index                                      │
│  - corresponding_authors                                                    │
└───────────────────────────────────────────────────────────────────────────┘
                     │
                     │ paperbrain summarize [--force-all]
                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │ OpenAI summarization + deterministic post-processing        │
      │ - paper card sections                                       │
      │ - person cards from corresponding authors                   │
      │ - topic cards from person big-questions (theme grouped)     │
      │ - figure/caption-aware key-result supplementation           │
      └──────────────┬──────────────────────────────────────────────┘
                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Card tables + links                                                      │
│  paper_cards     person_cards     topic_cards                            │
│  paper_person_links    paper_topic_links    person_topic_links           │
└───────────────────────────────────────────────────────────────────────────┘
                     │
                     │ paperbrain export --output-dir <path>
                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Markdown vault output                                                     │
│  index.md                                                                 │
│  papers/*.md                                                              │
│  people/*.md                                                              │
│  topics/*.md                                                              │
└───────────────────────────────────────────────────────────────────────────┘
```

### Card design (implemented)

```text
Paper card (papers/<slug>)
  Frontmatter:
    slug, type: paper, paper_type, title, authors[], journal, year
  Body:
    Corresponding authors: [[people/...]]
    Related topics: [[topics/...]]
    Article:
      - Key question solved
      - Why this question is important
      - How the paper solves this question
      - Key findings and flow
        * Logical flow of sections/experiments (numbered)
        * Key results with figure references (bulleted)
      - Limitations of the paper
    Review:
      - Key goal of the review
      - Key unsolved questions
      - Why these unsolved questions are important
      - Why these unsolved questions are still unsolved

Person card (people/<normalized-email>)
  Frontmatter:
    slug, type: person, name, email, affiliation
  Body:
    - Focus area
    - Big questions:
      * Question
      * Why important
      * Related papers
    Related papers / Related topics (wikilinks)

Topic card (topics/<normalized-theme>)
  Frontmatter:
    slug, type: topic, topic
  Body:
    - Topic
    - Related big questions:
      * Question
      * Why important
      * Related papers
      * Related people
    Related papers / Related people (wikilinks)
```

---

## 3. Installation

### Requirements
- Python **3.12+**
- PostgreSQL (with `pgvector` extension available)
- OpenAI API key

### Install package

```bash
cd /path/to/paperbrain
python3 -m pip install -e .
```

### Prepare database

1. Create a PostgreSQL database (example name: `paperbrain`)
2. Ensure extension can be created:
   - `CREATE EXTENSION IF NOT EXISTS vector;`

---

## 4. Configuration and bootstrap

### Write config (and optionally test connectivity)

```bash
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY
```

Default config path is:
- `config/paperbrain.conf`

Config shape:

```toml
[paperbrain]
database_url = "postgresql://<user>:<pass>@localhost:5432/paperbrain"
openai_api_key = "sk-..."
summary_model = "gpt-4.1-mini"
embedding_model = "text-embedding-3-small"
```

### Initialize schema

```bash
paperbrain init --url postgresql://<user>:<pass>@localhost:5432/paperbrain
```

Use `--force` to drop/recreate all tables:

```bash
paperbrain init --url postgresql://<user>:<pass>@localhost:5432/paperbrain --force
```

---

## 5. Command-line reference

| Command | Purpose | Key options |
|---|---|---|
| `paperbrain setup` | Save config and validate connections | `--url`, `--openai-api-key`, `--summary-model`, `--embedding-model`, `--config-path`, `--test-connections/--no-test-connections` |
| `paperbrain init` | Apply DB schema | `--url`, `--force` |
| `paperbrain ingest PATH` | Parse PDFs and store chunks/embeddings | `--recursive`, `--force-all`, `--config-path` |
| `paperbrain browse KEYWORD` | Keyword browse card bodies | `--type [paper\|person\|topic\|all]`, `--config-path` |
| `paperbrain search QUERY` | Hybrid keyword + vector paper search | `--top-k`, `--include-cards`, `--config-path` |
| `paperbrain summarize` | Build/update paper/person/topic cards | `--force-all`, `--config-path` |
| `paperbrain lint` | Run quality checks/fixes | `--config-path` |
| `paperbrain stats` | Show corpus counts | `--config-path` |
| `paperbrain export` | Export markdown vault files | `--output-dir`, `--config-path` |

---

## 6. Typical usage

### End-to-end run

```bash
# 1) Configure
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --openai-api-key $OPENAI_API_KEY

# 2) Initialize schema
paperbrain init --url postgresql://<user>:<pass>@localhost:5432/paperbrain --force

# 3) Ingest PDFs
paperbrain ingest /path/to/pdfs --recursive --force-all

# 4) Build cards
paperbrain summarize --force-all

# 5) Search
paperbrain search "gut microbiome and lung cancer" --top-k 10 --include-cards

# 6) Export markdown vault
paperbrain export --output-dir /path/to/exported_cards
```

### Expected export layout

```text
exported_cards/
  index.md
  papers/
    *.md
  people/
    *.md
  topics/
    *.md
```

---

## 7. Troubleshooting

### `psycopg is required for database connections`
Install dependencies in your active environment:
```bash
python3 -m pip install -e .
```

### `Database URL must start with postgresql://`
Use PostgreSQL URL format explicitly, e.g.:
```text
postgresql://user:pass@localhost:5432/paperbrain
```

### `CREATE EXTENSION vector` fails
Install/enable pgvector on your PostgreSQL instance, then run init again.

### OpenAI quota/auth errors
Check `OPENAI_API_KEY` value and account quota/status.

---

## 8. Development and tests

Run the full suite:

```bash
python3 -m pytest -q
```

Optional live integration test:

```bash
# Expected skip in non-live mode
python3 -m pytest -q tests/test_live_openai_pipeline.py

# Live mode
PAPERBRAIN_LIVE_TEST=1 \
PAPERBRAIN_ALLOW_DB_RESET=1 \
OPENAI_API_KEY=<your-openai-key> \
PAPERBRAIN_TEST_DATABASE_URL=postgresql://<user>:<pass>@localhost:5432/<db> \
python3 -m pytest -q tests/test_live_openai_pipeline.py
```
