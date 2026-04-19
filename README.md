# PaperBrain

PaperBrain is a Python CLI for building a local scientific knowledge base from PDFs.
It uses:
- **PostgreSQL + pgvector** for storage and hybrid retrieval
- **Marker (default) or Docling** for PDF parsing
- **OpenAI** for optional embeddings and OpenAI summaries
- **Markdown export** for Obsidian-style linked notes

---

## Core Concept

PaperBrain is a **card-system design** for a **scientific question-centric** paper digest:
- **question-centered paper cards** capture each paper's key question, reasoning, evidence, and limitations
- **person cards** track long-horizon big questions from linked papers
- **topic cards** group coherent cross-person themes

---

## 1. What PaperBrain does

PaperBrain focuses on a **question-centric workflow**:
1. Ingest PDFs and extract metadata/text for question-aware synthesis
2. Optionally build chunk embeddings for hybrid retrieval (disabled by default)
3. Generate structured **paper/person/topic** cards around questions and evidence
4. Link cards bidirectionally across questions, people, and topics
5. Export everything as markdown files for iterative question tracking

---

## 2. Data flow (ASCII, with question-centric card design detail)

```text
┌──────────────────────────────┐
│ Local PDFs (single file/dir) │
└──────────────┬───────────────┘
               │ paperbrain ingest [--recursive] [--force-all]
               │                  [--start-offset N] [--max-files N]
               │                  [--parse-worker-recycle-every N]
               ▼
      ┌─────────────────────────────┐
      │ MarkerParser (default)       │
      │ or DoclingParser             │
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
                     │ paperbrain summarize [--card-scope all|paper|person|topic]
                     ▼
      ┌─────────────────────────────────────────────────────────────┐
      │ Provider-selected summarization (OpenAI/Gemini/Ollama) +    │
      │ deterministic post-processing                               │
      │ - question-centered paper cards (Q/reasoning/evidence/lim)  │
      │ - person cards from corresponding-author big questions       │
      │ - topic cards from cross-person big-question themes          │
      │ - figure/caption-aware evidence supplementation              │
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
      - Primary question addressed
      - Why this question is important
      - Reasoning path used to answer the question
      - Key evidence and flow
        * Logical flow of sections/experiments (numbered)
        * Key results with figure references (bulleted)
      - Limitations of the paper
    Review:
      - Key review question
      - Key unsolved questions
      - Why these unsolved questions are important
      - Why these unsolved questions are still unsolved

Person card (people/<normalized-email>)
  Frontmatter:
    slug, type: person, name, email, affiliation
  Body:
    - Focus area
    - Big questions (long-horizon):
      * Question
      * Why important
      * Related papers
    Related papers / Related topics (wikilinks)

Topic card (topics/<normalized-theme>)
  Frontmatter:
    slug, type: topic, topic
  Body:
    - Topic
    - Related big questions (cross-person):
      * Question
      * Why important
      * Related papers
      * Related people
    Related papers / Related people (wikilinks)
```

---

## 3. Installation

### System Requirements

- **Python**: 3.12 or later
- **PostgreSQL**: 13+ with `pgvector` extension support
- **System packages** (Ubuntu/Debian):
  ```bash
  sudo apt-get install postgresql-client libpq-dev
  ```
  (macOS with Homebrew):
  ```bash
  brew install libpq
  ```

### API Keys (provider-dependent)

- **OpenAI**: Required only when either:
  - `summary_model` uses `openai:*`, or
  - embeddings are enabled with `--embeddings-enabled`
- **Summary provider** (choose one):
  - **OpenAI**: For GPT-4 mini summaries
  - **Google Gemini**: For Gemini 2.5 flash summaries
  - **Ollama**: For local/self-hosted LLM summaries

### Install PaperBrain

**From repository (recommended for development):**

```bash
git clone https://github.com/yourusername/paperbrain.git
cd paperbrain
python3 -m pip install -e .
```

This installs PaperBrain in editable mode with all core dependencies:
- `typer` — CLI framework
- `psycopg[binary]` — PostgreSQL driver
- `openai` — OpenAI API client (optional embeddings + OpenAI summaries)
- `google-genai` — Google Gemini API client
- `ollama` — Ollama API client
- `marker-pdf` — default PDF parsing
- `docling` — optional alternate parser (with optional OCR)
- `fastapi` + `uvicorn` — Internal web service (if needed)

**Via pip (released versions only):**

```bash
python3 -m pip install paperbrain
```

### Optional: Install with development tools

For development, testing, and linting:

```bash
cd paperbrain
python3 -m pip install -e ".[dev]"
```

(Note: Development dependencies are optional; install `pytest` manually if needed for testing.)

### Prepare PostgreSQL Database

1. Create a PostgreSQL database (example name: `paperbrain`):
   ```bash
   createdb paperbrain
   ```

2. Enable the `pgvector` extension (required for embeddings):
   ```bash
   psql paperbrain -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

3. Note your connection string for setup:
   ```
   postgresql://<user>:<password>@<host>:<port>/<dbname>
   # Example: postgresql://user:pass@localhost:5432/paperbrain
   ```

---

## 4. Configuration and bootstrap

### Write config (and optionally test connectivity)

```bash
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --summary-model openai:gpt-4.1-mini
```

For Gemini summary models, pass the Gemini key and a Gemini model name:

```bash
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --gemini-api-key $GEMINI_API_KEY \
  --summary-model gemini:gemini-2.5-flash
```

For Ollama summary models, pass the Ollama key and an `ollama:*` summary model.
You can also override the Ollama base URL:

```bash
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --ollama-api-key $OLLAMA_API_KEY \
  --summary-model ollama:llama3.2

# Optional custom Ollama endpoint
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --ollama-api-key $OLLAMA_API_KEY \
  --ollama-base-url https://ollama.example \
  --summary-model ollama:llama3.2

# Optional: enable embeddings + hybrid search
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --openai-api-key $OPENAI_API_KEY \
  --summary-model gemini:gemini-2.5-flash \
  --embeddings-enabled \
  --embedding-model text-embedding-3-small

# Optional: enable Docling OCR during parsing (default is off)
paperbrain setup \
  --url postgresql://<user>:<pass>@localhost:5432/paperbrain \
  --gemini-api-key $GEMINI_API_KEY \
  --summary-model gemini:gemini-2.5-flash \
  --pdf-parser docling \
  --ocr-enabled
```

Default config path is:
- `~/.config/paperbrain/paperbrain.conf`

Config shape:

```toml
[paperbrain]
database_url = "postgresql://<user>:<pass>@localhost:5432/paperbrain"
openai_api_key = "sk-..."
gemini_api_key = "AIza..."
ollama_api_key = "ol-..."
ollama_base_url = "https://ollama.com"
summary_model = "openai:gpt-4.1-mini"
embedding_model = "text-embedding-3-small"
embeddings_enabled = false
ocr_enabled = false
pdf_parser = "marker"
```

Summary provider is selected from explicit summary model prefixes:

- `openai:*` models use OpenAI for summaries
- `gemini:*` models use Gemini for summaries
- `ollama:*` models use Ollama for summaries

Legacy unprefixed selectors (for example `gpt-4.1-mini` or `gemini-2.5-flash`) are rejected.

Embedding behavior:

- Default is `embeddings_enabled = false`
- When disabled, ingest stores papers/chunks but skips vector generation
- Search automatically falls back to keyword-only ranking
- Enable embeddings with `--embeddings-enabled` for hybrid keyword + vector search

OCR behavior:

- `ocr_enabled` is required and shared by Marker and Docling parsers
- Default is `ocr_enabled = false`
- Enable OCR with `--ocr-enabled` for scanned/image-only PDFs
- Parser-specific OCR behavior follows the selected parser (`pdf_parser`)

PDF parser behavior:

- `pdf_parser` is required in config and must be `marker` or `docling`
- Default setup value is `pdf_parser = "marker"`
- Choose Docling with `--pdf-parser docling` when running `paperbrain setup`

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
| `paperbrain setup` | Save config and validate connections | `--url`, `--openai-api-key`, `--gemini-api-key`, `--ollama-api-key`, `--ollama-base-url`, `--summary-model`, `--embedding-model`, `--embeddings-enabled/--no-embeddings-enabled`, `--ocr-enabled/--no-ocr-enabled`, `--pdf-parser`, `--config-path`, `--test-connections/--no-test-connections` |
| `paperbrain init` | Apply DB schema | `--url`, `--force` |
| `paperbrain ingest PATH` | Parse PDFs and store chunks (embeddings optional) | `--recursive`, `--force-all`, `--start-offset`, `--max-files`, `--parse-worker-recycle-every`, `--config-path` |
| `paperbrain browse KEYWORD` | Keyword browse card bodies | `--type [paper\|person\|topic\|all]`, `--config-path` |
| `paperbrain search QUERY` | Hybrid search when enabled, keyword-only otherwise | `--top-k`, `--include-cards`, `--config-path` |
| `paperbrain summarize` | Build/update paper/person/topic cards | `--card-scope [all\|paper\|person\|topic]`, `--config-path` |
| `paperbrain lint` | Run quality checks/fixes | `--config-path` |
| `paperbrain stats` | Show corpus counts | `--config-path` |
| `paperbrain export` | Export markdown vault files | `--output-dir`, `--config-path` |

---

## 6. Typical usage

### End-to-end run

```bash
# 1) Configure
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --openai-api-key $OPENAI_API_KEY --summary-model openai:gpt-4.1-mini

# 1b) Or use Gemini for summaries
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --gemini-api-key $GEMINI_API_KEY --summary-model gemini:gemini-2.5-flash

# 1c) Or use Ollama for summaries (optional: add --ollama-base-url)
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --ollama-api-key $OLLAMA_API_KEY --summary-model ollama:llama3.2

# 1d) Optional: enable embeddings (for hybrid search)
paperbrain setup --url postgresql://<user>:<pass>@localhost:5432/paperbrain --gemini-api-key $GEMINI_API_KEY --summary-model gemini:gemini-2.5-flash --embeddings-enabled --openai-api-key $OPENAI_API_KEY

# 2) Initialize schema
paperbrain init --url postgresql://<user>:<pass>@localhost:5432/paperbrain --force

# 3) Ingest PDFs
paperbrain ingest /path/to/pdfs --recursive --force-all

# 4) Build cards (incremental default)
paperbrain summarize

# 5) Search
paperbrain search "gut microbiome and lung cancer" --top-k 10 --include-cards

# 6) Export markdown vault
paperbrain export --output-dir /path/to/exported_cards
```

Default summarize behavior is incremental related-card updates.

Use explicit summarize rebuild scopes only when needed:

```bash
paperbrain summarize --card-scope all
paperbrain summarize --card-scope paper
paperbrain summarize --card-scope person
paperbrain summarize --card-scope topic
```

### Large-corpus ingest (1000+ PDFs)

Use bounded ingest windows and parser worker recycling to keep memory stable:

```bash
# Process 200 files at a time, starting from offset 0
paperbrain ingest /path/to/pdfs --recursive --start-offset 0 --max-files 200 --parse-worker-recycle-every 5

# Resume next window
paperbrain ingest /path/to/pdfs --recursive --start-offset 200 --max-files 200 --parse-worker-recycle-every 5
```

`--parse-worker-recycle-every` defaults to `5` for both Marker and Docling parsers.

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

### Web Viewer (FastAPI + Tailwind)

```bash
uvicorn paperbrain.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open the web viewer to browse cards by tab, search quickly, view masonry-style card grids, and inspect full card details in the side panel.

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
