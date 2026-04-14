import json
from types import SimpleNamespace

import pytest

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


def test_openai_summary_adapter_person_generation_via_llm_from_linked_papers() -> None:
    class PersonLLMClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return json.dumps(
                    {
                        "focus_area": [],
                        "big_questions": [
                            {
                                "question": "How can microbiome stratification improve immunotherapy response?",
                                "why_important": "Enables precision treatment selection.",
                                "related_papers": ["papers/test-paper"],
                            }
                        ],
                    }
                )
            return "{}"

    client = PersonLLMClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    person_cards = adapter.derive_person_cards(
        [
            {
                "slug": "papers/test-paper",
                "title": "Test Paper",
                "summary": "Key question solved: Q",
                "corresponding_authors": ["Alice Example <alice@example.org>"],
            }
        ]
    )

    assert person_cards[0]["slug"] == "people/alice-example-org"
    assert person_cards[0]["big_questions"][0]["question"] == (
        "How can microbiome stratification improve immunotherapy response?"
    )
    assert person_cards[0]["focus_area"] == []
    assert any(call["text"].startswith("Generate person card JSON") for call in client.summary_calls)
    assert "papers/test-paper" in client.summary_calls[0]["text"]
    assert "Test Paper" in client.summary_calls[0]["text"]


def test_openai_summary_adapter_retries_person_generation_once_then_succeeds() -> None:
    class RetryPersonClient(FakeOpenAIClient):
        def __init__(self) -> None:
            super().__init__()
            self.person_attempts = 0

        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                self.person_attempts += 1
                if self.person_attempts == 1:
                    return "{not-json"
                return json.dumps(
                    {
                        "focus_area": [],
                        "big_questions": [
                            {
                                "question": "How do we robustly validate signatures?",
                                "why_important": "Avoids false biomarker claims.",
                                "related_papers": ["papers/test-paper"],
                            }
                        ],
                    }
                )
            return "{}"

    client = RetryPersonClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    cards = adapter.derive_person_cards(
        [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
    )

    assert cards[0]["big_questions"][0]["question"] == "How do we robustly validate signatures?"
    assert client.person_attempts == 2


def test_openai_summary_adapter_raises_after_second_invalid_person_generation_attempt() -> None:
    class AlwaysInvalidPersonClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return '{"focus_area": [], "big_questions": []}'
            return "{}"

    client = AlwaysInvalidPersonClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    with pytest.raises(ValueError, match=r"person generation failed after 2 attempts"):
        adapter.derive_person_cards(
            [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
        )


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

    assert paper_card["slug"] == "papers/test-paper"
    assert paper_card["type"] == "article"
    assert paper_card["paper_type"] == "article"
    assert paper_card["title"] == "Test Paper"
    assert paper_card["authors"] == []
    assert paper_card["journal"] == "Unknown"
    assert paper_card["year"] == 0
    assert paper_card["summary"].startswith("Key question solved:")
    assert paper_card["corresponding_authors"] == ["alice@example.org"]
    assert person_cards == [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "name": "alice",
                "email": "alice@example.org",
                "affiliation": "example.org",
                "focus_area": ["test paper"],
            "big_questions": [
                {
                    "question": "Test Paper",
                    "why_important": "(missing)",
                    "related_papers": ["papers/test-paper"],
                }
            ],
            "related_papers": ["papers/test-paper"],
        }
    ]
    assert topic_cards == [
        {
            "slug": "topics/test-paper",
            "type": "topic",
            "topic": "test paper",
            "related_big_questions": [
                {
                    "question": "Test Paper",
                    "why_important": "(missing)",
                    "related_papers": ["papers/test-paper"],
                    "related_people": ["people/alice-example-org"],
                }
            ],
            "related_people": ["people/alice-example-org"],
            "related_papers": ["papers/test-paper"],
        }
    ]
    assert len(client.summary_calls) == 2
    assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-page OCR/text")
    assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")
    assert "logical flow of sections and experiments" in client.summary_calls[1]["text"]
    assert "bullet points for key results with figure references" in client.summary_calls[1]["text"]


def test_openai_summary_adapter_infers_corresponding_authors_from_first_page_text() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    first_page = "Corresponding author: Alice Research alice@university.org"
    paper_text = first_page + "\n" + ("x" * 9000)

    paper_card = adapter.summarize_paper(
        paper_text,
        {
            "slug": "papers/test-paper",
            "title": "Test Paper",
            "corresponding_authors": [],
        },
    )

    assert paper_card["corresponding_authors"] == ["alice@university.org"]
    assert len(client.summary_calls) == 2
    assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-page OCR/text")
    assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")


def test_openai_summary_adapter_uses_openai_fallback_for_missing_corresponding_authors() -> None:
    class FallbackClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract corresponding author email addresses"):
                return '["bob@lab.org"]'
            return "generated summary"

    client = FallbackClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper_text = "No email on first page\n" + ("x" * 9000)

    paper_card = adapter.summarize_paper(
        paper_text,
        {
            "slug": "papers/test-paper",
            "title": "Test Paper",
            "corresponding_authors": [],
        },
    )

    assert paper_card["corresponding_authors"] == ["bob@lab.org"]
    assert len(client.summary_calls) == 3
    assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-page OCR/text")
    assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")
    assert client.summary_calls[2]["text"].startswith("Extract corresponding author email addresses")


def test_openai_summary_adapter_formats_logical_flow_list_as_numbered_markdown() -> None:
    class StructuredSummaryClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract bibliographic metadata"):
                return '{"authors": ["A"], "journal": "Nature", "year": 2025}'
            if text.startswith("Create a concise structured summary of the paper"):
                return """
{
  "paper_type": "article",
  "key_question_solved": "Q",
  "why_important": "W",
  "method": "M",
  "findings_logical_flow": [
    "Introduction sets up motivation.",
    "Figure 1 establishes baseline.",
    "Figure 2 validates mechanism."
  ],
  "key_results_with_figures": [
    {"figure": "Figure 1", "result": "Baseline trend is confirmed."},
    {"figure": "Figure 2", "result": "Mechanistic effect is significant."}
  ],
  "limitations": "L"
}
""".strip()
            return "generated summary"

    client = StructuredSummaryClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper = adapter.summarize_paper(
        "paper text",
        {"slug": "papers/test-paper", "title": "Test Paper", "corresponding_authors": ["alice@example.org"]},
    )

    assert "Logical flow of sections and experiments:" in paper["summary"]
    assert "1. Introduction sets up motivation." in paper["summary"]
    assert "2. Figure 1 establishes baseline." in paper["summary"]
    assert "3. Figure 2 validates mechanism." in paper["summary"]
    assert "['Introduction sets up motivation.'" not in paper["summary"]


def test_openai_summary_adapter_supplements_key_results_from_figure_mentions() -> None:
    class SparseResultClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract bibliographic metadata"):
                return '{"authors": ["A"], "journal": "Nature", "year": 2025}'
            if text.startswith("Create a concise structured summary of the paper"):
                return """
{
  "paper_type": "article",
  "key_question_solved": "Q",
  "why_important": "W",
  "method": "M",
  "findings_logical_flow": "Flow",
  "key_results_with_figures": [],
  "limitations": "L"
}
""".strip()
            return "generated summary"

    client = SparseResultClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper_text = (
        "Figure 1 shows baseline survival trends across cohorts. "
        "Figure 2 demonstrates treatment effect with reduced hazard ratio. "
        "Figure 3 validates robustness in an independent dataset."
    )
    paper = adapter.summarize_paper(
        paper_text,
        {"slug": "papers/test-paper", "title": "Test Paper", "corresponding_authors": ["alice@example.org"]},
    )

    assert "- Figure 1: shows baseline survival trends across cohorts" in paper["summary"]
    assert "- Figure 2: demonstrates treatment effect with reduced hazard ratio" in paper["summary"]
    assert "- Figure 3: validates robustness in an independent dataset" in paper["summary"]
    assert "- Figure ?: (missing)" not in paper["summary"]


def test_openai_summary_adapter_normalizes_supplementary_figure_labels() -> None:
    class SupplementaryClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Extract bibliographic metadata"):
                return '{"authors": ["A"], "journal": "Nature", "year": 2025}'
            if text.startswith("Create a concise structured summary of the paper"):
                return """
{
  "paper_type": "article",
  "key_question_solved": "Q",
  "why_important": "W",
  "method": "M",
  "findings_logical_flow": "Flow",
  "key_results_with_figures": [
    {"figure": "Figure S1", "result": "Supplementary benchmark result."}
  ],
  "limitations": "L"
}
""".strip()
            return "generated summary"

    client = SupplementaryClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    paper = adapter.summarize_paper(
        "Figure S1 reports supplementary benchmark result.",
        {"slug": "papers/test-paper", "title": "Test Paper", "corresponding_authors": ["alice@example.org"]},
    )

    assert "- Figure S1: Supplementary benchmark result." in paper["summary"]
    assert "Figure Figure S1" not in paper["summary"]


def test_topic_derivation_is_deterministic_and_data_driven() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    person_cards = [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": "How can gut microbiome signals improve lung cancer treatment response?",
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/a"],
                }
            ],
            "related_papers": ["papers/a"],
        },
        {
            "slug": "people/bob-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": "How does lung microbiome composition affect lung infection severity?",
                    "why_important": "May enable earlier intervention for respiratory disease.",
                    "related_papers": ["papers/b"],
                }
            ],
            "related_papers": ["papers/b"],
        },
    ]

    topic_cards = adapter.derive_topic_cards(person_cards)

    assert {card["slug"] for card in topic_cards} == {
        "topics/gut-microbiome-and-lung-cancer-treatment",
        "topics/lung-microbiome-and-lung-infection",
    }
    assert all(card["slug"] != "topics/research-synthesis" for card in topic_cards)
    cancer_microbiome_card = next(
        card for card in topic_cards if card["slug"] == "topics/gut-microbiome-and-lung-cancer-treatment"
    )
    lung_infection_card = next(card for card in topic_cards if card["slug"] == "topics/lung-microbiome-and-lung-infection")
    assert cancer_microbiome_card["topic"] == "gut microbiome and lung cancer treatment"
    assert cancer_microbiome_card["related_people"] == ["people/alice-example-org"]
    assert cancer_microbiome_card["related_papers"] == ["papers/a"]
    assert cancer_microbiome_card["related_big_questions"] == [
        {
            "question": "How can gut microbiome signals improve lung cancer treatment response?",
            "why_important": "Could personalize treatment and improve outcomes.",
            "related_papers": ["papers/a"],
            "related_people": ["people/alice-example-org"],
        }
    ]
    assert lung_infection_card["topic"] == "lung microbiome and lung infection"
    assert lung_infection_card["related_people"] == ["people/bob-example-org"]
    assert lung_infection_card["related_papers"] == ["papers/b"]
    assert lung_infection_card["related_big_questions"] == [
        {
            "question": "How does lung microbiome composition affect lung infection severity?",
            "why_important": "May enable earlier intervention for respiratory disease.",
            "related_papers": ["papers/b"],
            "related_people": ["people/bob-example-org"],
        }
    ]


def test_topic_derivation_merges_duplicate_big_questions_across_people() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    shared_question = "How can gut microbiome signals improve lung cancer treatment response?"
    person_cards = [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": shared_question,
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/a"],
                }
            ],
            "related_papers": ["papers/a"],
        },
        {
            "slug": "people/bob-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": shared_question,
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/b"],
                }
            ],
            "related_papers": ["papers/b"],
        },
    ]

    topic_cards = adapter.derive_topic_cards(person_cards)
    assert len(topic_cards) == 1
    assert topic_cards[0]["slug"] == "topics/gut-microbiome-and-lung-cancer-treatment"
    assert topic_cards[0]["related_people"] == ["people/alice-example-org", "people/bob-example-org"]
    assert topic_cards[0]["related_papers"] == ["papers/a", "papers/b"]
    assert topic_cards[0]["related_big_questions"] == [
        {
            "question": shared_question,
            "why_important": "Could personalize treatment and improve outcomes.",
            "related_papers": ["papers/a", "papers/b"],
            "related_people": ["people/alice-example-org", "people/bob-example-org"],
        }
    ]
