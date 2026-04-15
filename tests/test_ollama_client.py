import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_ollama_client_summarize_calls_chat() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def chat(self, *, model: str, messages: list[dict[str, str]]) -> SimpleNamespace:
            self.calls.append({"model": model, "messages": messages})
            return SimpleNamespace(message=SimpleNamespace(content="summary"))

    sdk_client = FakeSDKClient()
    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.example", sdk_client=sdk_client)

    client.summarize("paper text", model="qwen2.5")

    assert sdk_client.calls == [
        {
            "model": "qwen2.5",
            "messages": [{"role": "user", "content": "paper text"}],
        }
    ]


def test_ollama_client_summarize_strips_message_content() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def chat(self, *, model: str, messages: list[dict[str, str]]) -> SimpleNamespace:
            return SimpleNamespace(message=SimpleNamespace(content="  ollama summary  \n"))

    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.example", sdk_client=FakeSDKClient())

    summary = client.summarize("paper text", model="qwen2.5")

    assert summary == "ollama summary"


def test_ollama_client_summarize_handles_missing_content() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def chat(self, *, model: str, messages: list[dict[str, str]]) -> SimpleNamespace:
            return SimpleNamespace(message=SimpleNamespace())

    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.example", sdk_client=FakeSDKClient())

    summary = client.summarize("paper text", model="qwen2.5")

    assert summary == ""


def test_ollama_client_summarize_coerces_non_string_content() -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    class FakeSDKClient:
        def chat(self, *, model: str, messages: list[dict[str, str]]) -> SimpleNamespace:
            return SimpleNamespace(message=SimpleNamespace(content=123))

    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.example", sdk_client=FakeSDKClient())

    summary = client.summarize("paper text", model="qwen2.5")

    assert summary == "123"


def test_ollama_client_constructor_sets_auth_header_for_non_empty_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    sdk_client = object()
    client_ctor = Mock(return_value=sdk_client)
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=client_ctor))

    client = OllamaCloudClient(api_key="ol-test", base_url="https://ollama.example")

    client_ctor.assert_called_once_with(
        host="https://ollama.example",
        headers={"Authorization": "Bearer ol-test"},
    )
    assert client.sdk_client is sdk_client


@pytest.mark.parametrize("api_key", ["", "\n\t   "])
def test_ollama_client_constructor_omits_auth_for_blank_key(
    monkeypatch: pytest.MonkeyPatch, api_key: str
) -> None:
    from paperbrain.adapters.ollama_client import OllamaCloudClient

    sdk_client = object()
    client_ctor = Mock(return_value=sdk_client)
    monkeypatch.setitem(sys.modules, "ollama", SimpleNamespace(Client=client_ctor))

    client = OllamaCloudClient(api_key=api_key, base_url="https://ollama.example")

    client_ctor.assert_called_once_with(host="https://ollama.example", headers=None)
    assert client.sdk_client is sdk_client
