# Provider Troubleshooting

Use this table to map symptoms to next actions quickly.

| Symptom | Likely cause | Action | Diagnostic command |
|---|---|---|---|
| `Invalid username or token` | Bad API key/token or wrong provider account | Re-check the configured key for the selected provider, rotate if needed, and rerun a minimal summarize command. | `python3 -c 'import os; print("OPENAI_API_KEY set" if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY missing")'` |
| `401 Unauthorized` | Missing auth header or expired credential | Verify environment/config key is loaded in the active shell, then retry with the same model prefix. | `paperbrain summarize --config-path "$CONFIG_PATH"` |
| `403 Forbidden` | Key lacks model permission | Switch to an allowed model or update provider project permissions, then rerun summarize. | `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "openai:gpt-4o-mini" --config-path "$CONFIG_PATH" --test-connections` |
| `429 Too Many Requests` | Rate/quota exhaustion | Wait/backoff, reduce batch scope, and rerun. If persistent, check provider quota dashboard. | `paperbrain summarize --config-path "$CONFIG_PATH" && paperbrain stats --config-path "$CONFIG_PATH"` |
| `model not found` | Typo or unsupported model ID | Use explicit provider prefix and a valid model name (`openai:`, `gemini:`, `ollama:`). | `paperbrain setup --url "postgresql://localhost:5432/paperbrain" --summary-model "gemini:gemini-1.5-flash" --config-path "$CONFIG_PATH" --test-connections` |

## Quick isolation steps

1. Confirm the summary model includes a valid provider prefix.
2. Run one small summarize pass to reproduce quickly.
3. If auth errors continue, validate credentials outside the workflow, then retry.
