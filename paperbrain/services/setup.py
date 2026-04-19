from pathlib import Path

from paperbrain.adapters.ollama_client import OllamaCloudClient
from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDINGS_ENABLED,
    DEFAULT_PDF_PARSER,
    DEFAULT_SUMMARY_MODEL,
    ConfigStore,
    normalize_pdf_parser,
    validate_embedding_model_for_schema,
)
from paperbrain.db import connect

try:  # pragma: no cover - optional dependency
    from paperbrain.adapters.gemini_client import GeminiClient
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    GeminiClient = None  # type: ignore[assignment]

from paperbrain.summary_provider import parse_summary_model


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
    model: str,
) -> None:
    probe = "paperbrain connectivity check"
    client.summarize(probe, model=model)


def _validate_gemini_summary_connection(
    gemini_api_key: str,
    model: str,
) -> None:
    if not gemini_api_key.strip():
        raise ValueError("Gemini API key is required when testing connections")
    if GeminiClient is None:
        raise RuntimeError("Gemini client is not available")
    client = GeminiClient(api_key=gemini_api_key)
    probe = "paperbrain connectivity check"
    client.summarize(probe, model=model)


def _validate_ollama_summary_connection(
    ollama_api_key: str,
    ollama_base_url: str,
    model: str,
) -> None:
    if not ollama_api_key.strip():
        raise ValueError("Ollama API key is required when testing connections")
    normalized_base_url = ollama_base_url.strip()
    if not normalized_base_url:
        raise ValueError("Ollama base URL is required when testing connections")
    client = OllamaCloudClient(api_key=ollama_api_key, base_url=normalized_base_url)
    probe = "paperbrain connectivity check"
    client.summarize(probe, model=model)


def run_setup(
    database_url: str,
    openai_api_key: str = "",
    gemini_api_key: str = "",
    ollama_api_key: str = "",
    ollama_base_url: str = "https://ollama.com",
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embeddings_enabled: bool = DEFAULT_EMBEDDINGS_ENABLED,
    docling_ocr_enabled: bool = False,
    pdf_parser: str = DEFAULT_PDF_PARSER,
    config_path: Path = Path.home() / ".config" / "paperbrain" / "paperbrain.conf",
    test_connections: bool = True,
) -> str:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")
    if not summary_model.strip():
        raise ValueError("Summary model must be non-empty")
    if not embedding_model.strip():
        raise ValueError("Embedding model must be non-empty")
    if embeddings_enabled:
        validate_embedding_model_for_schema(embedding_model)
    normalized_pdf_parser = normalize_pdf_parser(pdf_parser)
    # parse provider:model explicitly (always validate prefix)
    parsed = parse_summary_model(summary_model)
    if test_connections:
        try:
            _validate_database_connection(database_url)
        except Exception as exc:
            raise RuntimeError(f"Setup failed during database validation: {exc}") from exc
        summary_uses_openai = parsed.provider == "openai"
        summary_uses_gemini = parsed.provider == "gemini"
        summary_uses_ollama = parsed.provider == "ollama"
        try:
            openai_client: OpenAIClient | None = None
            if embeddings_enabled:
                openai_client = _validate_openai_embedding_connection(
                    openai_api_key=openai_api_key,
                    embedding_model=embedding_model,
                )
            if summary_uses_openai:
                if openai_client is None:
                    if not openai_api_key.strip():
                        raise ValueError("OpenAI API key is required when testing connections")
                    openai_client = OpenAIClient(api_key=openai_api_key)
                _validate_openai_summary_connection(openai_client, parsed.model)
        except Exception as exc:
            raise RuntimeError(f"Setup failed during OpenAI validation: {exc}") from exc
        if summary_uses_gemini:
            try:
                _validate_gemini_summary_connection(
                    gemini_api_key=gemini_api_key,
                    model=parsed.model,
                )
            except Exception as exc:
                raise RuntimeError(f"Setup failed during Gemini validation: {exc}") from exc
        if summary_uses_ollama:
            try:
                _validate_ollama_summary_connection(
                    ollama_api_key=ollama_api_key,
                    ollama_base_url=ollama_base_url,
                    model=parsed.model,
                )
            except Exception as exc:
                raise RuntimeError(f"Setup failed during Ollama validation: {exc}") from exc
    store = ConfigStore(config_path)
    store.save(
        database_url=database_url,
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        ollama_api_key=ollama_api_key,
        ollama_base_url=ollama_base_url,
        summary_model=summary_model,
        embedding_model=embedding_model,
        embeddings_enabled=embeddings_enabled,
        docling_ocr_enabled=docling_ocr_enabled,
        pdf_parser=normalized_pdf_parser,
    )
    return f"Saved configuration to {config_path}"
