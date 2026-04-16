from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "paperbrain-workflow"
SKILL_FILE = SKILL_DIR / "SKILL.md"
EXPECTED_FRONTMATTER = {
    "name": "paperbrain-workflow",
    "description": "Run and troubleshoot PaperBrain ingest/summarize/export workflows with validation and duplicate checks.",
}
REQUIRED_FILES = [
    SKILL_FILE,
    SKILL_DIR / "references" / "commands.md",
    SKILL_DIR / "references" / "provider-troubleshooting.md",
    SKILL_DIR / "references" / "dedupe-and-export-checks.md",
]
REQUIRED_SECTIONS = [
    "## When to use this skill",
    "## Workflow checklist",
    "## Validation loop",
    "## Completion gate",
]
REQUIRED_PREFIXES = ["openai:", "gemini:", "ollama:"]
REQUIRED_TRIGGERS = [
    "Read `references/commands.md` before running workflow commands.",
    "If provider auth fails, read `references/provider-troubleshooting.md`.",
    "If duplicate exports are suspected, read `references/dedupe-and-export-checks.md`.",
]
REFERENCE_EXPECTATIONS = {
    "commands.md": "python3 -m pytest -q",
    "provider-troubleshooting.md": "Invalid username or token",
    "dedupe-and-export-checks.md": "source_path",
}


def test_skill_package_files_exist() -> None:
    for path in REQUIRED_FILES:
        assert path.exists(), f"Missing required skill file: {path}"


def test_skill_frontmatter_has_required_metadata() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "---"
    assert "---" in lines[1:]
    frontmatter_end = lines[1:].index("---") + 1
    frontmatter_lines = lines[1:frontmatter_end]
    metadata = dict(line.split(": ", maxsplit=1) for line in frontmatter_lines)
    assert metadata == EXPECTED_FRONTMATTER


def test_skill_markdown_omits_agent_name_mentions() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8").lower()
    assert "openclaw" not in content
    assert "hermes" not in content


def test_skill_markdown_contains_required_sections() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in content


def test_skill_markdown_requires_provider_prefixes() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    for prefix in REQUIRED_PREFIXES:
        assert prefix in content


def test_skill_markdown_contains_reference_triggers() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    for trigger in REQUIRED_TRIGGERS:
        assert trigger in content


def test_reference_documents_include_required_content() -> None:
    references_dir = SKILL_DIR / "references"
    for file_name, expected_text in REFERENCE_EXPECTATIONS.items():
        content = (references_dir / file_name).read_text(encoding="utf-8")
        assert expected_text in content
