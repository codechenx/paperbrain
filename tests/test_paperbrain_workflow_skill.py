from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "paperbrain-workflow"
SKILL_FILE = SKILL_DIR / "SKILL.md"
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
    assert content.startswith("---\n")
    assert "name:" in content
    assert "description:" in content


def test_skill_markdown_omits_agent_name_mentions() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8").lower()
    assert "openclaw" not in content
    assert "hermes" not in content
