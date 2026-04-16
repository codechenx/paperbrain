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
REQUIRED_COMPLETION_FIELDS = [
    "`provider_model`",
    "`baseline_checks`",
    "`ingest_result`",
    "`summarize_result`",
    "`export_result`",
    "`counts`",
    "`skipped_categories`",
    "`failure_categories`",
    "`validation_findings`",
    "`next_actions`",
]
REQUIRED_FAILURE_DETAIL_FIELDS = [
    "`symptom`",
    "`likely_cause`",
    "`diagnostic_command`",
]
REFERENCE_EXPECTATIONS = {
    "commands.md": 'paperbrain summarize --config-path "$CONFIG_PATH"',
    "provider-troubleshooting.md": "## OpenAI",
    "dedupe-and-export-checks.md": "`source_path` mismatch check (absolute vs relative)",
}
PROVIDER_DIAGNOSTIC_COMMANDS = {
    "Invalid username or token": 'python3 -c \'import os; print("OPENAI_API_KEY set" if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY missing")\'',
    "401 Unauthorized": 'paperbrain summarize --config-path "$CONFIG_PATH"',
    "403 Forbidden": 'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "openai:gpt-4o-mini" --config-path "$CONFIG_PATH" --test-connections',
    "429 Too Many Requests": 'paperbrain summarize --config-path "$CONFIG_PATH" && paperbrain stats --config-path "$CONFIG_PATH"',
    "model not found": 'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "gemini:gemini-1.5-flash" --config-path "$CONFIG_PATH" --test-connections',
}
PROVIDER_SPECIFIC_GUIDANCE = {
    "## OpenAI": [
        "OPENAI_API_KEY",
        'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "openai:gpt-4o-mini" --config-path "$CONFIG_PATH" --test-connections',
    ],
    "## Gemini": [
        "GEMINI_API_KEY",
        'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "gemini:gemini-1.5-flash" --config-path "$CONFIG_PATH" --test-connections',
    ],
    "## Ollama": [
        "OLLAMA_HOST",
        'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "ollama:llama3.1" --config-path "$CONFIG_PATH" --test-connections',
    ],
}
CANONICAL_WORKFLOW_COMMANDS = [
    'paperbrain ingest /abs/path/to/pdfs --recursive --config-path "$CONFIG_PATH"',
    'paperbrain summarize --config-path "$CONFIG_PATH"',
    'paperbrain export --output-dir /abs/path/to/export --config-path "$CONFIG_PATH"',
]
POST_STEP_VERIFICATION_COMMANDS = [
    'paperbrain stats --config-path "$CONFIG_PATH"',
    'paperbrain search "<title keyword>" --top-k 3 --include-cards --config-path "$CONFIG_PATH"',
    "find /abs/path/to/export -maxdepth 2 -type d | sort",
    "test -f /abs/path/to/export/index.md",
]
DEDUPE_MISMATCH_FLOW_MARKERS = [
    "Absolute path example:",
    "Relative path example:",
    "Normalize both paths to the same base directory and compare the resolved result.",
    "treat this as a path-format mismatch (not distinct sources)",
]


def _section_block(content: str, header: str) -> str:
    start = content.index(header)
    tail = content[start:]
    next_header = tail.find("\n## ", len(header))
    if next_header == -1:
        return tail
    return tail[:next_header]


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


def test_skill_completion_gate_requires_reporting_fields() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    completion_gate = _section_block(content, "## Completion gate")
    for field in REQUIRED_COMPLETION_FIELDS:
        assert field in completion_gate
    for field in REQUIRED_FAILURE_DETAIL_FIELDS:
        assert field in completion_gate


def test_reference_documents_include_required_content() -> None:
    references_dir = SKILL_DIR / "references"
    for file_name, expected_text in REFERENCE_EXPECTATIONS.items():
        content = (references_dir / file_name).read_text(encoding="utf-8")
        assert expected_text in content


def test_provider_troubleshooting_includes_diagnostic_commands_per_category() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    for category, command in PROVIDER_DIAGNOSTIC_COMMANDS.items():
        assert category in content
        assert command in content


def test_provider_troubleshooting_has_provider_specific_diagnostics_and_actions() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    for section, expected_snippets in PROVIDER_SPECIFIC_GUIDANCE.items():
        block = _section_block(content, section)
        for snippet in expected_snippets:
            assert snippet in block


def test_commands_reference_includes_canonical_patterns_with_config_path() -> None:
    content = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    for command in CANONICAL_WORKFLOW_COMMANDS:
        assert command in content


def test_commands_reference_includes_post_step_verification_commands() -> None:
    content = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    for command in POST_STEP_VERIFICATION_COMMANDS:
        assert command in content


def test_dedupe_reference_includes_source_path_mismatch_flow() -> None:
    content = (SKILL_DIR / "references" / "dedupe-and-export-checks.md").read_text(
        encoding="utf-8"
    )
    positions = [content.index(marker) for marker in DEDUPE_MISMATCH_FLOW_MARKERS]
    assert positions == sorted(positions)
