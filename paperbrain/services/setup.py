from pathlib import Path

from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_SUMMARY_MODEL
from paperbrain.config import ConfigStore, validate_embedding_model_for_schema
from paperbrain.db import connect

try:  # pragma: no cover - optional dependency
    from paperbrain.adapters.gemini_client import GeminiClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    GeminiClient = None  # type: ignore[assignment]


def _validate_database_connection(database_url: str) -> None:
    with connect(database_url):
        return None


def _validate_openai_embedding_connection(
    openai_api_key: str,
    embedding_model: str,
) -> OpenAIClient:
    if not openai_api_key.strip():
        raise ValueError("OpenAI API key is required when testing connections")
    client = OpenAIClient(api_key=openai_api_key)
    probe = "paperbrain connectivity check"
    client.embed([probe], model=embedding_model)
    return client


def _validate_openai_summary_connection(
    client: OpenAIClient,
    summary_model: str,
) -> None:
    probe = "paperbrain connectivity check"
    client.summarize(probe, model=summary_model)


def _validate_gemini_summary_connection(
    gemini_api_key: str,
    summary_model: str,
) -> None:
    if not gemini_api_key.strip():
        raise ValueError("Gemini API key is required when testing connections")
    if GeminiClient is None:
        raise RuntimeError("Gemini client is not available")
    client = GeminiClient(api_key=gemini_api_key)
    probe = "paperbrain connectivity check"
    client.summarize(probe, model=summary_model)


def _is_gemini_summary_model(summary_model: str) -> bool:
    return summary_model.strip().lower().startswith("gemini-")


def run_setup(
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    config_path: Path = Path("./config/paperbrain.conf"),
    test_connections: bool = True,
) -> str:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")
    if not summary_model.strip():
        raise ValueError("Summary model must be non-empty")
    if not embedding_model.strip():
        raise ValueError("Embedding model must be non-empty")
    validate_embedding_model_for_schema(embedding_model)
    if test_connections:
        try:
            _validate_database_connection(database_url)
        except Exception as exc:
            raise RuntimeError(f"Setup failed during database validation: {exc}") from exc
        summary_uses_gemini = _is_gemini_summary_model(summary_model)
        try:
            openai_client = _validate_openai_embedding_connection(
                openai_api_key=openai_api_key,
                embedding_model=embedding_model,
            )
            if not summary_uses_gemini:
                _validate_openai_summary_connection(openai_client, summary_model)
        except Exception as exc:
            raise RuntimeError(f"Setup failed during OpenAI validation: {exc}") from exc
        if summary_uses_gemini:
            try:
                _validate_gemini_summary_connection(
                    gemini_api_key=gemini_api_key,
                    summary_model=summary_model,
                )
            except Exception as exc:
                raise RuntimeError(f"Setup failed during Gemini validation: {exc}") from exc
    store = ConfigStore(config_path)
    store.save(
        database_url=database_url,
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        summary_model=summary_model,
        embedding_model=embedding_model,
    )
    return f"Saved configuration to {config_path}"
