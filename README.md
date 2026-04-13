# PaperBrain

PaperBrain is a Python CLI scaffold for a local, question-centric research knowledge base using Postgres + pgvector.

## Commands

- `paperbrain setup`
- `paperbrain init`
- `paperbrain ingest`
- `paperbrain browse`
- `paperbrain search`
- `paperbrain summarize`
- `paperbrain lint`
- `paperbrain stats`
- `paperbrain export`

## Development

Run tests:

```bash
python3 -m pytest -q
```

### Optional live integration test (OpenAI + Postgres + local PDFs)

Live pipeline testing is opt-in and skipped by default.

```bash
# Non-live mode (expected: skipped)
python3 -m pytest -q tests/test_live_openai_pipeline.py

# Live mode (runs setup/init/ingest/summarize through CLI)
PAPERBRAIN_LIVE_TEST=1 \
OPENAI_API_KEY=<your-openai-key> \
PAPERBRAIN_TEST_DATABASE_URL=postgresql://<user>:<pass>@localhost:5432/<db> \
python3 -m pytest -q tests/test_live_openai_pipeline.py
```
