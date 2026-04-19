from dataclasses import dataclass

from paperbrain.adapters.parser_factory import build_pdf_parser
from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.adapters.llm import LLMAdapter, GeminiSummaryAdapter, OllamaSummaryAdapter, OpenAISummaryAdapter
from paperbrain.adapters.gemini_client import GeminiClient
from paperbrain.adapters.ollama_client import OllamaCloudClient
from paperbrain.adapters.embedding import OpenAIEmbeddingAdapter
from paperbrain.config import ConfigStore


@dataclass(frozen=True, slots=True)
class ParsedSummaryModel:
    provider: str
    model: str


def parse_summary_model(summary_model: str) -> ParsedSummaryModel:
    raw = (summary_model or "").strip()
    if ":" not in raw:
        raise ValueError("Summary model must be prefixed with one of: openai:, gemini:, ollama:")
    provider, model = raw.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()
    allowed = {"openai", "gemini", "ollama"}
    if provider not in allowed:
        raise ValueError(f"Unknown summary provider prefix: {provider}")
    if not model:
        raise ValueError(f"{provider.capitalize()} summary model must include a model name after '{provider}:'")
    return ParsedSummaryModel(provider=provider, model=model)


class SummaryProvider:
    def __init__(self, config_path):
        self.config = ConfigStore(config_path).load()
        self.summary_model = self.config.summary_model
        # validate and parse explicit provider:model syntax
        self.parsed = parse_summary_model(self.summary_model)
        self.openai_client = self._build_openai_client()
        self.llm = self._build_llm()
        self.parser = build_pdf_parser(
            self.config.pdf_parser,
            ocr_enabled=self.config.ocr_enabled,
        )
        self.embeddings = self._build_embeddings()

    def _build_openai_client(self) -> OpenAIClient | None:
        needs_openai_client = self.parsed.provider == "openai" or self.config.embeddings_enabled
        if not needs_openai_client:
            return None
        if not self.config.openai_api_key.strip():
            if self.config.embeddings_enabled:
                raise ValueError("OpenAI API key is required for embeddings")
            raise ValueError("OpenAI API key is required for OpenAI summary models")
        return OpenAIClient(api_key=self.config.openai_api_key)

    def _build_embeddings(self) -> OpenAIEmbeddingAdapter | None:
        if not self.config.embeddings_enabled:
            return None
        if self.openai_client is None:
            raise ValueError("OpenAI API key is required for embeddings")
        return OpenAIEmbeddingAdapter(client=self.openai_client, model=self.config.embedding_model)

    def _build_llm(self) -> LLMAdapter:
        provider = self.parsed.provider
        model = self.parsed.model
        if provider == "gemini":
            if not self.config.gemini_api_key.strip():
                raise ValueError("Gemini API key is required for Gemini summary models")
            summary_client = GeminiClient(api_key=self.config.gemini_api_key)
            return GeminiSummaryAdapter(client=summary_client, model=model)
        elif provider == "ollama":
            if not self.config.ollama_api_key.strip():
                raise ValueError("Ollama API key is required for Ollama summary models")
            if not self.config.ollama_base_url.strip():
                raise ValueError("Ollama base URL is required for Ollama summary models")
            summary_client = OllamaCloudClient(api_key=self.config.ollama_api_key, base_url=self.config.ollama_base_url.strip())
            return OllamaSummaryAdapter(client=summary_client, model=model)
        else:
            if self.openai_client is None:
                raise ValueError("OpenAI API key is required for OpenAI summary models")
            return OpenAISummaryAdapter(client=self.openai_client, model=model)
