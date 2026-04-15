from types import SimpleNamespace


def test_gemini_client_summarize_calls_generate_content_and_strips_output() -> None:
    from paperbrain.adapters.gemini_client import GeminiClient

    class FakeModelsAPI:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_content(self, *, model: str, contents: str) -> SimpleNamespace:
            self.calls.append({"model": model, "contents": contents})
            return SimpleNamespace(text="  gemini summary output  \n")

    class FakeSDKClient:
        def __init__(self) -> None:
            self.models = FakeModelsAPI()

    sdk_client = FakeSDKClient()
    client = GeminiClient(api_key="gm-test", sdk_client=sdk_client)

    summary = client.summarize("paper text", model="gemini-2.5-flash")

    assert summary == "gemini summary output"
    assert sdk_client.models.calls == [
        {"model": "gemini-2.5-flash", "contents": "paper text"}
    ]
