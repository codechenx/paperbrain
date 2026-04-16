import json
import re
from copy import deepcopy
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
REQUIRED_CHECKLIST_POST_RUN_VALIDATION = (
    "Post-run validation: reconcile run counts, report skipped categories, and run dedupe/export sanity checks."
)
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
RUN_SUMMARY_TEMPLATE_HEADER = "### Scenario run-summary template"
RUN_SUMMARY_REQUIRED_KEYS = [
    "provider_model",
    "baseline_checks",
    "ingest_result",
    "summarize_result",
    "export_result",
    "counts",
    "skipped_categories",
    "failure_categories",
    "failure_details",
    "validation_findings",
    "next_actions",
]
RUN_SUMMARY_NESTED_REQUIRED_KEYS = {
    "ingest_result": ["scope", "command", "outcome"],
    "summarize_result": ["command", "outcome", "evidence"],
    "export_result": ["output_path", "file_layout_evidence"],
}
NORMAL_RUN_FLOW_CONTRACT_HEADER = "### Scenario: normal run flow contract"
NORMAL_RUN_FLOW_ORDERED_STEPS = [
    "Run baseline checks from `references/commands.md`.",
    "Set `CONFIG_PATH` and verify connectivity with `paperbrain stats --config-path \"$CONFIG_PATH\"`.",
    "Run ingest and capture `scope`, `command`, and `outcome`.",
    "Run summarize and capture command outcome plus card/update evidence.",
    "Run export and verify `index.md` plus `papers/`, `people/`, and `topics/` layout.",
    "Emit completion report using the `Scenario run-summary template` fields.",
]
PROVIDER_AUTH_FLOW_HEADER = "## Scenario: provider-auth failure flow contract"
PROVIDER_AUTH_FLOW_ORDERED_STEPS = [
    "Classify the auth symptom (`Invalid username or token`, `401 Unauthorized`, or `403 Forbidden`).",
    "Run the mapped diagnostic command and ensure it uses `--config-path \"$CONFIG_PATH\"` where applicable.",
    "Apply provider-specific remediation (credential rotation, permission/model fix, or config correction).",
    "Rerun `paperbrain summarize --config-path \"$CONFIG_PATH\"` minimally, then rerun export only if summarize succeeds.",
    "Report failure details with `symptom`, `likely_cause`, and `diagnostic_command` plus remediation status.",
]
PROVIDER_AUTH_TEMPLATE_HEADER = "### Scenario provider-auth report template"
PROVIDER_AUTH_TEMPLATE_REQUIRED_KEYS = [
    "scenario",
    "provider_model",
    "symptom",
    "likely_cause",
    "diagnostic_command",
    "remediation",
    "rerun_command",
    "next_action",
]
DUPLICATE_EXPORT_FLOW_HEADER = "## Scenario: duplicate-export/source_path mismatch flow contract"
DUPLICATE_EXPORT_FLOW_ORDERED_STEPS = [
    "Capture the suspect duplicate pair and compare filename + slug first.",
    "Classify path style using one absolute path and one relative path example.",
    "Normalize both paths against the same base directory and compare resolved outputs.",
    "If normalized paths match, treat as path-format mismatch and dedupe the extra record.",
    "Rerun summarize, rerun export, and verify layout (`index.md`, `papers/`, `people/`, `topics/`).",
]
DUPLICATE_EXPORT_TEMPLATE_HEADER = "### Scenario duplicate-export report template"
DUPLICATE_EXPORT_TEMPLATE_REQUIRED_KEYS = [
    "scenario",
    "record_pair",
    "absolute_source_path",
    "relative_source_path",
    "normalized_match",
    "dedupe_action",
    "rerun_steps",
    "verification",
]
DEFAULT_CONFIG_PATH = "~/.config/paperbrain/paperbrain.conf"
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
        "ollama_api_key",
        "ollama_base_url",
        "Optional local mode",
        'paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "ollama:llama3.1" --config-path "$CONFIG_PATH" --test-connections',
    ],
}
OLLAMA_CONFIG_PATH_SNIPPETS = [
    'CONFIG_PATH="${CONFIG_PATH:-${HOME}/.config/paperbrain/paperbrain.conf}"',
    'os.environ["CONFIG_PATH"]',
]
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
FAIL_FAST_POLICY_MARKERS = [
    "no silent fallbacks",
    "no provider auto-switching",
    "provider/model errors must be surfaced and fixed",
]
EXPORT_LAYOUT_MARKERS = ("index.md", "papers/", "people/", "topics/")


def _section_block(content: str, header: str) -> str:
    start = content.index(header)
    tail = content[start:]
    next_header = tail.find("\n## ", len(header))
    if next_header == -1:
        return tail
    return tail[:next_header]


def _json_block_after_header(content: str, header: str) -> dict:
    start = content.index(header)
    tail = content[start + len(header) :]
    match = re.search(r"```json\n(.*?)\n```", tail, re.DOTALL)
    assert match is not None, f"Missing JSON block after header: {header}"
    return json.loads(match.group(1))


def _assert_markers_in_order(content: str, markers: list[str]) -> None:
    positions = [content.index(marker) for marker in markers]
    assert positions == sorted(positions)


def _validate_payload_shape(payload: dict, template: dict, path: str = "root") -> list[str]:
    errors: list[str] = []
    for key, expected_value in template.items():
        if key not in payload:
            errors.append(f"{path}.{key} missing")
            continue
        value = payload[key]
        if isinstance(expected_value, dict):
            if not isinstance(value, dict):
                errors.append(f"{path}.{key} should be object")
                continue
            errors.extend(_validate_payload_shape(value, expected_value, f"{path}.{key}"))
        elif isinstance(expected_value, list) and not isinstance(value, list):
            errors.append(f"{path}.{key} should be list")
    return errors


def _simulate_scenario_execution(
    scenario: str, contract_block: str, payload: dict, template: dict, execution: dict
) -> tuple[bool, list[str]]:
    errors = _validate_payload_shape(payload, template)

    if scenario == "normal-run":
        if "Scenario run-summary template" not in contract_block:
            errors.append("normal-run contract should reference run-summary template")
        if not all(execution.get(flag) for flag in ("baseline_ok", "ingest_ok", "summarize_ok", "export_ok")):
            errors.append("normal-run execution requires baseline/ingest/summarize/export success")
        if payload.get("failure_categories") not in ("none", []):
            errors.append("normal-run should not report active failure_categories")
        if payload.get("next_actions") != "none":
            errors.append("normal-run should conclude with next_actions=none")
        layout_evidence = payload.get("export_result", {}).get("file_layout_evidence", "")
        for marker in EXPORT_LAYOUT_MARKERS:
            if marker not in layout_evidence:
                errors.append(f"normal-run export evidence missing {marker}")

    elif scenario == "provider-auth-failure":
        if "rerun export only if summarize succeeds" not in contract_block:
            errors.append("provider-auth contract missing summarize-before-export gate")
        if "$CONFIG_PATH" not in payload.get("diagnostic_command", ""):
            errors.append("provider-auth diagnostic_command must include $CONFIG_PATH")
        if not execution.get("diagnostic_ran"):
            errors.append("provider-auth execution must run diagnostic command")
        if execution.get("export_rerun_attempted") and not execution.get("summarize_rerun_ok"):
            errors.append("provider-auth must not rerun export before summarize succeeds")

    elif scenario == "duplicate-export-source-path-mismatch":
        if "treat as path-format mismatch and dedupe the extra record" not in contract_block:
            errors.append("duplicate-export contract missing path-format mismatch guidance")
        if payload.get("normalized_match") is not True:
            errors.append("duplicate-export scenario requires normalized_match=true")
        if not execution.get("dedupe_applied"):
            errors.append("duplicate-export execution must dedupe the extra record")
        if not all(
            execution.get(flag) for flag in ("summarize_rerun_ok", "export_rerun_ok", "layout_verified")
        ):
            errors.append("duplicate-export execution requires summarize/export rerun and layout verification")
    else:
        errors.append(f"unsupported scenario: {scenario}")

    return not errors, errors


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


def test_skill_workflow_checklist_requires_post_run_validation_wording() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    checklist = _section_block(content, "## Workflow checklist")
    assert REQUIRED_CHECKLIST_POST_RUN_VALIDATION in checklist


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


def test_skill_run_summary_scenario_template_has_required_structure() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    template = _json_block_after_header(content, RUN_SUMMARY_TEMPLATE_HEADER)
    for key in RUN_SUMMARY_REQUIRED_KEYS:
        assert key in template
    for key, nested_keys in RUN_SUMMARY_NESTED_REQUIRED_KEYS.items():
        assert isinstance(template[key], dict)
        for nested_key in nested_keys:
            assert nested_key in template[key]
    assert isinstance(template["counts"], dict)
    assert isinstance(template["failure_details"], list)
    assert template["failure_details"], "failure_details should include at least one scenario item"
    for key in ("symptom", "likely_cause", "diagnostic_command"):
        assert key in template["failure_details"][0]


def test_skill_normal_run_flow_contract_has_ordered_steps() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    block = _section_block(content, NORMAL_RUN_FLOW_CONTRACT_HEADER)
    _assert_markers_in_order(block, NORMAL_RUN_FLOW_ORDERED_STEPS)


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


def test_provider_and_skill_docs_define_fail_fast_provider_model_policy() -> None:
    skill_content = SKILL_FILE.read_text(encoding="utf-8").lower()
    provider_content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    ).lower()
    combined = "\n".join((skill_content, provider_content))
    for marker in FAIL_FAST_POLICY_MARKERS:
        assert marker in combined


def test_provider_auth_failure_flow_contract_has_ordered_steps() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    block = _section_block(content, PROVIDER_AUTH_FLOW_HEADER)
    _assert_markers_in_order(block, PROVIDER_AUTH_FLOW_ORDERED_STEPS)


def test_provider_auth_failure_report_template_has_required_fields() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    template = _json_block_after_header(content, PROVIDER_AUTH_TEMPLATE_HEADER)
    for key in PROVIDER_AUTH_TEMPLATE_REQUIRED_KEYS:
        assert key in template
    assert template["scenario"] == "provider-auth-failure"
    assert template["rerun_command"] == 'paperbrain summarize --config-path "$CONFIG_PATH"'
    assert "$CONFIG_PATH" in template["diagnostic_command"]


def test_scenario_execution_normal_run_contract_passes() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    contract = _section_block(content, NORMAL_RUN_FLOW_CONTRACT_HEADER)
    template = _json_block_after_header(content, RUN_SUMMARY_TEMPLATE_HEADER)
    payload = deepcopy(template)
    payload["summarize_result"]["outcome"] = "success (42 cards updated)"
    payload["failure_categories"] = []
    payload["failure_details"] = []
    payload["next_actions"] = "none"
    payload["export_result"]["file_layout_evidence"] = "index.md + papers/ + people/ + topics/ verified"
    passed, errors = _simulate_scenario_execution(
        "normal-run",
        contract,
        payload,
        template,
        execution={"baseline_ok": True, "ingest_ok": True, "summarize_ok": True, "export_ok": True},
    )
    assert passed, errors


def test_provider_troubleshooting_has_provider_specific_diagnostics_and_actions() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    for section, expected_snippets in PROVIDER_SPECIFIC_GUIDANCE.items():
        block = _section_block(content, section)
        for snippet in expected_snippets:
            assert snippet in block


def test_scenario_execution_provider_auth_contract_rejects_export_before_summarize_success() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    contract = _section_block(content, PROVIDER_AUTH_FLOW_HEADER)
    template = _json_block_after_header(content, PROVIDER_AUTH_TEMPLATE_HEADER)
    payload = deepcopy(template)
    payload["next_action"] = "rerun summarize first; do not rerun export yet"

    passed, errors = _simulate_scenario_execution(
        "provider-auth-failure",
        contract,
        payload,
        template,
        execution={"diagnostic_ran": True, "summarize_rerun_ok": False, "export_rerun_attempted": True},
    )
    assert not passed
    assert "provider-auth must not rerun export before summarize succeeds" in errors


def test_provider_troubleshooting_ollama_env_var_is_only_optional_local_mode() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    ollama_block = _section_block(content, "## Ollama")
    if "OLLAMA_HOST" in ollama_block:
        assert "optional local mode" in ollama_block.lower()


def test_provider_troubleshooting_ollama_diagnostic_uses_config_path_variable() -> None:
    content = (SKILL_DIR / "references" / "provider-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    ollama_block = _section_block(content, "## Ollama")
    for snippet in OLLAMA_CONFIG_PATH_SNIPPETS:
        assert snippet in ollama_block
    assert 'Path.home() / ".config/paperbrain/paperbrain.conf"' not in ollama_block


def test_commands_reference_includes_canonical_patterns_with_config_path() -> None:
    content = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    for command in CANONICAL_WORKFLOW_COMMANDS:
        assert command in content


def test_commands_reference_includes_post_step_verification_commands() -> None:
    content = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    for command in POST_STEP_VERIFICATION_COMMANDS:
        assert command in content


def test_commands_reference_uses_default_config_path() -> None:
    content = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    assert DEFAULT_CONFIG_PATH in content
    assert "config.toml" not in content


def test_dedupe_reference_includes_source_path_mismatch_flow() -> None:
    content = (SKILL_DIR / "references" / "dedupe-and-export-checks.md").read_text(
        encoding="utf-8"
    )
    positions = [content.index(marker) for marker in DEDUPE_MISMATCH_FLOW_MARKERS]
    assert positions == sorted(positions)


def test_duplicate_export_flow_contract_has_ordered_steps() -> None:
    content = (SKILL_DIR / "references" / "dedupe-and-export-checks.md").read_text(
        encoding="utf-8"
    )
    block = _section_block(content, DUPLICATE_EXPORT_FLOW_HEADER)
    _assert_markers_in_order(block, DUPLICATE_EXPORT_FLOW_ORDERED_STEPS)


def test_duplicate_export_report_template_has_required_fields() -> None:
    content = (SKILL_DIR / "references" / "dedupe-and-export-checks.md").read_text(
        encoding="utf-8"
    )
    template = _json_block_after_header(content, DUPLICATE_EXPORT_TEMPLATE_HEADER)
    for key in DUPLICATE_EXPORT_TEMPLATE_REQUIRED_KEYS:
        assert key in template
    assert template["scenario"] == "duplicate-export-source-path-mismatch"
    assert isinstance(template["record_pair"], list)
    assert isinstance(template["rerun_steps"], list)
    assert template["rerun_steps"] == [
        'paperbrain summarize --config-path "$CONFIG_PATH"',
        'paperbrain export --output-dir /abs/path/to/export --config-path "$CONFIG_PATH"',
    ]


def test_scenario_execution_duplicate_export_contract_validates_path_match_and_reruns() -> None:
    content = (SKILL_DIR / "references" / "dedupe-and-export-checks.md").read_text(
        encoding="utf-8"
    )
    contract = _section_block(content, DUPLICATE_EXPORT_FLOW_HEADER)
    template = _json_block_after_header(content, DUPLICATE_EXPORT_TEMPLATE_HEADER)

    passing_payload = deepcopy(template)
    passed, errors = _simulate_scenario_execution(
        "duplicate-export-source-path-mismatch",
        contract,
        passing_payload,
        template,
        execution={
            "dedupe_applied": True,
            "summarize_rerun_ok": True,
            "export_rerun_ok": True,
            "layout_verified": True,
        },
    )
    assert passed, errors

    failing_payload = deepcopy(template)
    failing_payload["normalized_match"] = False
    failed, failure_errors = _simulate_scenario_execution(
        "duplicate-export-source-path-mismatch",
        contract,
        failing_payload,
        template,
        execution={
            "dedupe_applied": True,
            "summarize_rerun_ok": True,
            "export_rerun_ok": True,
            "layout_verified": True,
        },
    )
    assert not failed
    assert "duplicate-export scenario requires normalized_match=true" in failure_errors
