from types import SimpleNamespace


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
