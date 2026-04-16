# Provider Troubleshooting

Use this table to map symptoms to next actions quickly.

| Symptom | Likely cause | Action | Diagnostic command |
|---|---|---|---|
| `Invalid username or token` | Bad API key/token or wrong provider account | Re-check the configured key for the selected provider, rotate if needed, and rerun a minimal summarize command. | `python3 -c 'import os; print("OPENAI_API_KEY set" if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY missing")'` |
| `401 Unauthorized` | Missing auth header or expired credential | Verify environment/config key is loaded in the active shell, then retry with the same model prefix. | `paperbrain summarize --config-path "$CONFIG_PATH"` |
| `403 Forbidden` | Key lacks model permission | Switch to an allowed model or update provider project permissions, then rerun summarize. | `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "openai:gpt-4o-mini" --config-path "$CONFIG_PATH" --test-connections` |
| `429 Too Many Requests` | Rate/quota exhaustion | Wait/backoff, reduce batch scope, and rerun. If persistent, check provider quota dashboard. | `paperbrain summarize --config-path "$CONFIG_PATH" && paperbrain stats --config-path "$CONFIG_PATH"` |
| `model not found` | Typo or unsupported model ID | Use explicit provider prefix and a valid model name (`openai:`, `gemini:`, `ollama:`). | `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "gemini:gemini-1.5-flash" --config-path "$CONFIG_PATH" --test-connections` |

## OpenAI

- Diagnostics:
  - `python3 -c 'import os; print("OPENAI_API_KEY set" if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY missing")'`
  - `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "openai:gpt-4o-mini" --config-path "$CONFIG_PATH" --test-connections`
- Actions:
  - Rotate/regenerate `OPENAI_API_KEY` and reload shell environment.
  - Confirm the selected `openai:` model is enabled for the account/project.

## Gemini

- Diagnostics:
  - `python3 -c 'import os; print("GEMINI_API_KEY set" if os.getenv("GEMINI_API_KEY") else "GEMINI_API_KEY missing")'`
  - `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "gemini:gemini-1.5-flash" --config-path "$CONFIG_PATH" --test-connections`
- Actions:
  - Regenerate `GEMINI_API_KEY` if auth fails and verify it is exported in the active shell.
  - Verify the selected `gemini:` model is available to the configured Google AI project.

## Ollama

- Use `CONFIG_PATH="${CONFIG_PATH:-${HOME}/.config/paperbrain/paperbrain.conf}"` to target either default or custom configs.
- Diagnostics:
  - `CONFIG_PATH="${CONFIG_PATH:-${HOME}/.config/paperbrain/paperbrain.conf}" python3 -c 'import os, pathlib, tomllib; p = pathlib.Path(os.path.expanduser(os.environ["CONFIG_PATH"])); cfg = tomllib.loads(p.read_text(encoding="utf-8")).get("paperbrain", {}) if p.exists() else {}; print("ollama_api_key + ollama_base_url set" if str(cfg.get("ollama_api_key", "")).strip() and str(cfg.get("ollama_base_url", "")).strip() else "missing ollama_api_key or ollama_base_url")'`
  - `ollama list`
  - `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "ollama:llama3.1" --config-path "$CONFIG_PATH" --test-connections`
- Actions:
  - Set `ollama_api_key` and `ollama_base_url` in `paperbrain.conf`, then rerun summarize.
  - Pull the configured `ollama:` model (`ollama pull llama3.1`) before retrying summarize.
  - Optional local mode: if you intentionally run a local Ollama daemon, set `OLLAMA_HOST` to the daemon endpoint and re-run diagnostics.

## Scenario: provider-auth failure flow contract

1. Classify the auth symptom (`Invalid username or token`, `401 Unauthorized`, or `403 Forbidden`).
2. Run the mapped diagnostic command and ensure it uses `--config-path "$CONFIG_PATH"` where applicable.
3. Apply provider-specific remediation (credential rotation, permission/model fix, or config correction).
4. Rerun `paperbrain summarize --config-path "$CONFIG_PATH"` minimally, then rerun export only if summarize succeeds.
5. Report failure details with `symptom`, `likely_cause`, and `diagnostic_command` plus remediation status.

### Scenario provider-auth report template

```json
{
  "scenario": "provider-auth-failure",
  "provider_model": "openai:gpt-4o-mini",
  "symptom": "401 Unauthorized",
  "likely_cause": "expired API token",
  "diagnostic_command": "paperbrain summarize --config-path \"$CONFIG_PATH\"",
  "remediation": "rotated OPENAI_API_KEY and reloaded shell",
  "rerun_command": "paperbrain summarize --config-path \"$CONFIG_PATH\"",
  "next_action": "if summarize passes, rerun export with the same config path"
}
```

## Quick isolation steps

1. Confirm the summary model includes a valid provider prefix.
2. Run one small summarize pass to reproduce quickly.
3. If auth errors continue, validate credentials outside the workflow, then retry.
