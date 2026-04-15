from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULT_SUMMARY_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
SUPPORTED_1536D_EMBEDDING_MODELS = {DEFAULT_EMBEDDING_MODEL}


@dataclass(slots=True)
class AppConfig:
    database_url: str
    openai_api_key: str
    summary_model: str
    embedding_model: str
    gemini_api_key: str = ""


def validate_embedding_model_for_schema(embedding_model: str) -> None:
    model = embedding_model.strip()
    if model not in SUPPORTED_1536D_EMBEDDING_MODELS:
        supported = ", ".join(sorted(SUPPORTED_1536D_EMBEDDING_MODELS))
        raise ValueError(
            f"Embedding model '{embedding_model}' is incompatible with vector(1536). "
            f"Supported model(s): {supported}."
        )


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(
        self,
        database_url: str,
        openai_api_key: str = "",
        gemini_api_key: str = "",
        summary_model: str = DEFAULT_SUMMARY_MODEL,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        validate_embedding_model_for_schema(embedding_model)
        body = (
            "[paperbrain]\n"
            'database_url = "{database_url}"\n'
            'openai_api_key = "{openai_api_key}"\n'
            'gemini_api_key = "{gemini_api_key}"\n'
            'summary_model = "{summary_model}"\n'
            'embedding_model = "{embedding_model}"\n'
        ).format(
            database_url=database_url.replace("\\", "\\\\").replace('"', '\\"'),
            openai_api_key=openai_api_key.replace("\\", "\\\\").replace('"', '\\"'),
            gemini_api_key=gemini_api_key.replace("\\", "\\\\").replace('"', '\\"'),
            summary_model=summary_model.replace("\\", "\\\\").replace('"', '\\"'),
            embedding_model=embedding_model.replace("\\", "\\\\").replace('"', '\\"'),
        )
        self.path.write_text(body, encoding="utf-8")
        self.path.chmod(0o600)

    def load(self) -> AppConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.path}")
        parsed = tomllib.loads(self.path.read_text(encoding="utf-8"))
        section = parsed.get("paperbrain")
        if not isinstance(section, dict):
            raise ValueError("Missing [paperbrain] section in configuration file")
        database_url = section.get("database_url")
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("Missing non-empty database_url in configuration file")
        openai_api_key = section.get("openai_api_key", "")
        if not isinstance(openai_api_key, str):
            raise ValueError("Invalid openai_api_key in configuration file")
        gemini_api_key = section.get("gemini_api_key", "")
        if not isinstance(gemini_api_key, str):
            raise ValueError("Invalid gemini_api_key in configuration file")
        summary_model = section.get("summary_model", DEFAULT_SUMMARY_MODEL)
        if not isinstance(summary_model, str):
            raise ValueError("Invalid summary_model in configuration file")
        embedding_model = section.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
        if not isinstance(embedding_model, str):
            raise ValueError("Invalid embedding_model in configuration file")
        validate_embedding_model_for_schema(embedding_model)
        return AppConfig(
            database_url=database_url,
            openai_api_key=openai_api_key,
            summary_model=summary_model,
            embedding_model=embedding_model,
            gemini_api_key=gemini_api_key,
        )
