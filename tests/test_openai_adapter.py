from types import SimpleNamespace

from paperbrain.adapters.embedding import OpenAIEmbeddingAdapter
from paperbrain.adapters.llm import OpenAISummaryAdapter
from paperbrain.adapters.openai_client import OpenAIClient


class FakeEmbeddingsAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        self.calls.append({"model": model, "input": input})
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2]),
                SimpleNamespace(embedding=[0.3, 0.4]),
            ]
        )


class FakeResponsesAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, *, model: str, input: str) -> SimpleNamespace:
        self.calls.append({"model": model, "input": input})
        return SimpleNamespace(output_text="  summary output \n")


class FakeSDKClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddingsAPI()
        self.responses = FakeResponsesAPI()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.embed_calls: list[dict] = []
        self.summary_calls: list[dict] = []

    def embed(self, chunks: list[str], model: str) -> list[list[float]]:
        self.embed_calls.append({"chunks": chunks, "model": model})
        return [[0.5, 0.6]]

    def summarize(self, text: str, model: str) -> str:
        self.summary_calls.append({"text": text, "model": model})
        return "generated summary"


def test_openai_client_calls_embedding_and_summary() -> None:
    sdk_client = FakeSDKClient()
    client = OpenAIClient(api_key="test-key", sdk_client=sdk_client)

    vectors = client.embed(["chunk 1", "chunk 2"], model="text-embedding-3-small")
    summary = client.summarize("paper text", model="gpt-4.1-mini")

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert summary == "summary output"
    assert sdk_client.embeddings.calls == [
        {"model": "text-embedding-3-small", "input": ["chunk 1", "chunk 2"]}
    ]
    assert sdk_client.responses.calls == [{"model": "gpt-4.1-mini", "input": "paper text"}]


def test_openai_embedding_adapter_uses_client_with_configured_model() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAIEmbeddingAdapter(client=client, model="text-embedding-3-small")

    vectors = adapter.embed(["chunk 1"])

    assert vectors == [[0.5, 0.6]]
    assert client.embed_calls == [{"chunks": ["chunk 1"], "model": "text-embedding-3-small"}]


def test_openai_summary_adapter_preserves_person_topic_derivation() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper_text = "x" * 9000

    paper_card = adapter.summarize_paper(
        paper_text,
        {
            "slug": "papers/test-paper",
            "title": "Test Paper",
            "corresponding_authors": ["Alice Example <alice@example.org>"],
        },
    )
    person_cards = adapter.derive_person_cards([paper_card])
    topic_cards = adapter.derive_topic_cards(person_cards)

    assert paper_card == {
        "slug": "papers/test-paper",
        "type": "article",
        "title": "Test Paper",
        "summary": "generated summary",
        "corresponding_authors": ["Alice Example <alice@example.org>"],
    }
    assert person_cards == [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "email": "alice@example.org",
            "focus_area": "Research synthesis",
        }
    ]
    assert topic_cards == [
        {
            "slug": "topics/research-synthesis",
            "type": "topic",
            "topic": "Research Synthesis",
        }
    ]
    assert client.summary_calls == [{"text": f"Test Paper\n\n{paper_text[:8000]}", "model": "gpt-4.1-mini"}]
