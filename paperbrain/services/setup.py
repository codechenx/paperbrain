from pathlib import Path

from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_SUMMARY_MODEL
from paperbrain.config import ConfigStore, validate_embedding_model_for_schema
from paperbrain.db import connect


def _validate_database_connection(database_url: str) -> None:
    with connect(database_url):
        return None


def _validate_openai_connection(
    openai_api_key: str,
    summary_model: str,
    embedding_model: str,
) -> None:
    if not openai_api_key.strip():
        raise ValueError("OpenAI API key is required when testing connections")
    client = OpenAIClient(api_key=openai_api_key)
    probe = "paperbrain connectivity check"
    client.embed([probe], model=embedding_model)
    client.summarize(probe, model=summary_model)


def run_setup(
    database_url: str,
    openai_api_key: str = "",
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
        try:
            _validate_openai_connection(
                openai_api_key=openai_api_key,
                summary_model=summary_model,
                embedding_model=embedding_model,
            )
        except Exception as exc:
            raise RuntimeError(f"Setup failed during OpenAI validation: {exc}") from exc
    store = ConfigStore(config_path)
    store.save(
        database_url=database_url,
        openai_api_key=openai_api_key,
        summary_model=summary_model,
        embedding_model=embedding_model,
    )
    return f"Saved configuration to {config_path}"
