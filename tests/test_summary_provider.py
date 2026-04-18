import pytest
from pathlib import Path
from paperbrain.summary_provider import SummaryProvider
from paperbrain.config import ConfigStore


class DummyConfig:
    def __init__(self):
        self.summary_model = "openai:gpt-3.5-turbo"
        self.openai_api_key = "sk-test"
        self.embedding_model = "text-embedding-3-small"
        self.embeddings_enabled = True
        self.docling_ocr_enabled = False
        self.gemini_api_key = ""
        self.ollama_api_key = ""
        self.ollama_base_url = ""


class DummyConfigStore:
    def __init__(self, config_path):
        pass

    def load(self):
        return DummyConfig()


def test_summary_provider_openai(monkeypatch):
    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", DummyConfigStore)
    provider = SummaryProvider(config_path=Path("dummy"))
    assert provider.llm is not None
    assert provider.parser is not None
    assert provider.embeddings is not None
    assert provider.config.summary_model == "openai:gpt-3.5-turbo"


def test_summary_provider_passes_docling_ocr_setting(monkeypatch):
    captured = {}

    class OcrEnabledConfig(DummyConfig):
        def __init__(self):
            super().__init__()
            self.docling_ocr_enabled = True

    class OcrEnabledConfigStore:
        def __init__(self, config_path):
            pass

        def load(self):
            return OcrEnabledConfig()

    class FakeDoclingParser:
        def __init__(self, *, ocr_enabled=False):
            captured["ocr_enabled"] = ocr_enabled

    monkeypatch.setattr("paperbrain.summary_provider.ConfigStore", OcrEnabledConfigStore)
    monkeypatch.setattr("paperbrain.summary_provider.DoclingParser", FakeDoclingParser)

    SummaryProvider(config_path=Path("dummy"))

    assert captured["ocr_enabled"] is True
