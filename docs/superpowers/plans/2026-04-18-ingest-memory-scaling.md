# Ingest Memory Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ingest reliable for 1000+ PDFs by isolating Docling memory, streaming paper processing, and adding deterministic batch/resume controls.

**Architecture:** Introduce a process-isolated Docling parse worker that can be recycled after a fixed number of files, then wire ingest to consume parse results one paper at a time with bounded memory. Add CLI flags for offset/limit/recycle cadence so large runs can be segmented and resumed predictably without changing existing ingest defaults.

**Tech Stack:** Python 3.12, Typer CLI, multiprocessing, Docling, pytest

---

## File Structure

- Create: `paperbrain/adapters/docling_worker.py` (subprocess parser lifecycle + IPC protocol)
- Modify: `paperbrain/services/ingest.py` (file slicing, worker lifecycle, recycle behavior)
- Modify: `paperbrain/cli.py` (new ingest flags and wiring)
- Modify: `paperbrain/adapters/docling.py` (add converter reuse helper for worker process)
- Modify: `tests/test_ingest_service.py` (service-level batching/recycle tests)
- Modify: `tests/test_setup_command.py` (CLI ingest wiring tests, same file already used for runtime wiring)
- Modify: `README.md` (new ingest flags and large-corpus guidance)

---

### Task 1: Add failing tests for ingest batching controls

**Files:**
- Modify: `tests/test_ingest_service.py`
- Modify: `tests/test_setup_command.py`
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Write failing service tests for `start_offset` and `max_files`**

```python
def test_ingest_service_applies_start_offset_and_max_files(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    service = IngestService(repo=repo, parser=parser, embeddings=embeddings, chunk_size_words=3)

    files = []
    for name in ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]:
        p = tmp_path / name
        p.write_text("fake", encoding="utf-8")
        files.append(str(p))

    inserted = service.ingest_paths(
        files,
        force_all=False,
        recursive=False,
        start_offset=1,
        max_files=2,
        parse_worker_recycle_every=25,
    )

    assert inserted == 2
    assert [path.name for path in parser.calls] == ["b.pdf", "c.pdf"]
```

- [ ] **Step 2: Write failing CLI wiring test for new ingest flags**

```python
def test_cli_ingest_passes_batching_flags(monkeypatch: Any, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}

    class FakeIngestService:
        def __init__(self, *, repo: Any, parser: Any, embeddings: Any) -> None:
            _ = repo, parser, embeddings

        def ingest_paths(
            self,
            paths: list[str],
            force_all: bool,
            recursive: bool = False,
            start_offset: int = 0,
            max_files: int | None = None,
            parse_worker_recycle_every: int = 25,
        ) -> int:
            calls["args"] = (paths, force_all, recursive, start_offset, max_files, parse_worker_recycle_every)
            return 1
```

- [ ] **Step 3: Run tests and verify RED**

Run:
`python3 -m pytest -q tests/test_ingest_service.py tests/test_setup_command.py -k "start_offset or max_files or batching_flags"`

Expected:
- FAIL with unexpected keyword argument errors or missing CLI options.

- [ ] **Step 4: Commit test-only RED state**

```bash
git add tests/test_ingest_service.py tests/test_setup_command.py
git commit -m "test: add failing ingest batching flag coverage"
```

---

### Task 2: Implement ingest slicing and CLI flag wiring

**Files:**
- Modify: `paperbrain/services/ingest.py`
- Modify: `paperbrain/cli.py`
- Test: `tests/test_ingest_service.py`
- Test: `tests/test_setup_command.py`

- [ ] **Step 1: Implement service API for batching args**

```python
def ingest_paths(
    self,
    paths: list[str],
    force_all: bool,
    recursive: bool = False,
    start_offset: int = 0,
    max_files: int | None = None,
    parse_worker_recycle_every: int = 25,
) -> int:
    files = self._discover_files(paths, recursive=recursive)
    if start_offset < 0:
        raise ValueError("start_offset must be >= 0")
    if max_files is not None and max_files < 0:
        raise ValueError("max_files must be >= 0")
    selected = files[start_offset:]
    if max_files is not None:
        selected = selected[:max_files]
```

- [ ] **Step 2: Add ingest CLI options and validation**

```python
def ingest(
    path: Path = typer.Argument(Path("."), exists=True),
    force_all: bool = typer.Option(False, "--force-all"),
    recursive: bool = typer.Option(False, "--recursive"),
    start_offset: int = typer.Option(0, "--start-offset"),
    max_files: int | None = typer.Option(None, "--max-files"),
    parse_worker_recycle_every: int = typer.Option(25, "--parse-worker-recycle-every"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
) -> None:
    if start_offset < 0:
        raise typer.BadParameter("Must be >= 0", param_hint="'--start-offset'")
    if max_files is not None and max_files < 0:
        raise typer.BadParameter("Must be >= 0", param_hint="'--max-files'")
    if parse_worker_recycle_every <= 0:
        raise typer.BadParameter("Must be > 0", param_hint="'--parse-worker-recycle-every'")
```

- [ ] **Step 3: Run focused tests and verify GREEN**

Run:
`python3 -m pytest -q tests/test_ingest_service.py tests/test_setup_command.py -k "start_offset or max_files or batching_flags"`

Expected:
- PASS.

- [ ] **Step 4: Commit batching implementation**

```bash
git add paperbrain/services/ingest.py paperbrain/cli.py tests/test_ingest_service.py tests/test_setup_command.py
git commit -m "feat: add ingest batching and resume controls"
```

---

### Task 3: Add process-isolated Docling worker with recycling

**Files:**
- Create: `paperbrain/adapters/docling_worker.py`
- Modify: `paperbrain/adapters/docling.py`
- Modify: `paperbrain/services/ingest.py`
- Test: `tests/test_ingest_service.py`

- [ ] **Step 1: Add failing tests for worker recycle cadence**

```python
def test_ingest_service_recycles_parse_worker_after_threshold(tmp_path: Path) -> None:
    calls: list[str] = []
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    files: list[str] = []
    for name in ["a.pdf", "b.pdf", "c.pdf"]:
        p = tmp_path / name
        p.write_text("fake", encoding="utf-8")
        files.append(str(p))

    class FakeWorker:
        def parse(self, path: Path) -> FakeParsedPaper:
            calls.append(path.name)
            return parser.parse_pdf(path)
        def close(self) -> None:
            calls.append("closed")

    service = IngestService(
        repo=repo,
        parser=parser,
        embeddings=embeddings,
        chunk_size_words=3,
        parse_worker_factory=lambda: FakeWorker(),
    )
    inserted = service.ingest_paths(files, force_all=False, parse_worker_recycle_every=2)

    assert inserted == 3
    assert calls.count("closed") >= 2
```

- [ ] **Step 2: Implement worker module**

```python
# paperbrain/adapters/docling_worker.py
class DoclingWorker:
    def __init__(self) -> None:
        self._process = _spawn_worker_process()

    def parse(self, path: Path) -> ParsedPaper:
        return _rpc_parse(self._process, str(path))

    def close(self) -> None:
        _rpc_shutdown(self._process)
```

- [ ] **Step 3: Wire worker lifecycle into ingest service**

```python
worker = self._create_parse_worker()
try:
    for index, file_path in enumerate(selected, start=1):
        parsed = worker.parse(file_path)
        chunks = chunk_words(parsed.full_text, self.chunk_size_words)
        vectors = self.embeddings.embed(chunks) if self.embeddings is not None else []
        paper_id = self.repo.upsert_paper(parsed, force=force_all)
        self.repo.replace_chunks(paper_id, chunks, vectors)
        if index % parse_worker_recycle_every == 0:
            worker.close()
            worker = self._create_parse_worker()
finally:
    worker.close()
```

- [ ] **Step 4: Run worker-focused tests**

Run:
`python3 -m pytest -q tests/test_ingest_service.py -k "recycle or worker"`

Expected:
- PASS.

- [ ] **Step 5: Commit worker isolation**

```bash
git add paperbrain/adapters/docling_worker.py paperbrain/adapters/docling.py paperbrain/services/ingest.py tests/test_ingest_service.py
git commit -m "feat: isolate docling parsing in recyclable worker process"
```

---

### Task 4: Add failure-path coverage and CLI regression checks

**Files:**
- Modify: `tests/test_ingest_service.py`
- Modify: `tests/test_setup_command.py`

- [ ] **Step 1: Add failing test for worker crash propagation**

```python
def test_ingest_service_surfaces_worker_failure_with_file_context(tmp_path: Path) -> None:
    repo = FakeRepo()
    parser = FakeParser()
    embeddings = FakeEmbeddings()
    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class BrokenWorker:
        def parse(self, path: Path) -> FakeParsedPaper:
            raise RuntimeError("worker crashed")
        def close(self) -> None:
            return None

    service = IngestService(
        repo=repo,
        parser=parser,
        embeddings=embeddings,
        chunk_size_words=3,
        parse_worker_factory=lambda: BrokenWorker(),
    )
    with pytest.raises(RuntimeError, match="worker crashed"):
        service.ingest_paths([str(pdf_path)], force_all=False, parse_worker_recycle_every=25)
```

- [ ] **Step 2: Add failing test for invalid CLI values**

```python
def test_cli_ingest_rejects_non_positive_recycle_value() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "tests/pdf", "--parse-worker-recycle-every", "0"])
    assert result.exit_code == 2
    assert "Must be > 0" in result.output
```

- [ ] **Step 3: Run focused tests and verify GREEN**

Run:
`python3 -m pytest -q tests/test_ingest_service.py tests/test_setup_command.py -k "worker_failure or recycle_value"`

Expected:
- PASS.

- [ ] **Step 4: Commit reliability tests**

```bash
git add tests/test_ingest_service.py tests/test_setup_command.py
git commit -m "test: cover ingest worker failure and cli validation paths"
```

---

### Task 5: Documentation updates and full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document new ingest options and 1000+ PDF guidance**

```markdown
paperbrain ingest /path/to/pdfs --recursive --start-offset 0 --max-files 200 --parse-worker-recycle-every 25
paperbrain ingest /path/to/pdfs --recursive --start-offset 200 --max-files 200 --parse-worker-recycle-every 25
```

- [ ] **Step 2: Run target regressions**

Run:
`python3 -m pytest -q tests/test_ingest_service.py tests/test_setup_command.py`

Expected:
- PASS.

- [ ] **Step 3: Run full suite**

Run:
`python3 -m pytest -q`

Expected:
- PASS.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md
git commit -m "docs: add large-corpus ingest batching and worker recycle guidance"
```
