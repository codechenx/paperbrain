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
