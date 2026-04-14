import json
from types import SimpleNamespace

import pytest

from paperbrain.adapters.embedding import OpenAIEmbeddingAdapter
from paperbrain.adapters.llm import DeterministicLLMAdapter, OpenAISummaryAdapter
from paperbrain.adapters.openai_client import OpenAIClient
import paperbrain.adapters.llm as llm_module


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
        if text.startswith("Generate person card JSON"):
            title_match = next(
                (
                    line.split("title:", 1)[1].strip()
                    for line in text.splitlines()
                    if "title:" in line
                ),
                "Research question",
            )
            related = "papers/test-paper" if "papers/test-paper" in text else "papers/test"
            return json.dumps(
                {
                    "focus_area": [],
                    "big_questions": [
                        {
                            "question": title_match,
                            "why_important": "(missing)",
                            "related_papers": [related],
                        }
                    ],
                }
            )
        if text.startswith("Generate topic card JSON"):
            return json.dumps(
                [
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
            )
        return "generated summary"


def test_llm_module_no_longer_exposes_legacy_heuristic_symbols() -> None:
    assert not hasattr(llm_module, "_infer_theme_from_text")
    assert not hasattr(llm_module, "_derive_person_cards")
    assert not hasattr(llm_module, "_derive_topic_cards")
    assert not hasattr(llm_module, "DeterministicLLMAdapter")


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


def test_openai_summary_adapter_person_big_questions_from_linked_papers_via_llm() -> None:
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
    person_generation_calls = [
        call for call in client.summary_calls if call["text"].startswith("Generate person card JSON")
    ]
    assert len(person_generation_calls) == 1
    assert "papers/test-paper" in person_generation_calls[0]["text"]
    assert "Test Paper" in person_generation_calls[0]["text"]


def test_openai_summary_adapter_paper_summary_prompt_includes_reviewer_role_and_rubric() -> None:
    client = FakeOpenAIClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    adapter.summarize_paper(
        "paper text",
        {
            "slug": "papers/test-paper",
            "title": "Test Paper",
            "corresponding_authors": ["alice@example.org"],
        },
    )

    prompt = next(
        call["text"]
        for call in client.summary_calls
        if call["text"].startswith("Create a concise structured summary of the paper")
    )
    assert "senior reviewer for a top-tier scientific journal" in prompt
    assert "innovation, impact, and logical rigor" in prompt
    assert "Evidence boundary: Use only the supplied paper text. No external facts, assumptions, or citations." in prompt
    assert "method-to-result coherence" in prompt
    assert "strict JSON only" in prompt


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


def test_openai_summary_adapter_retries_when_person_focus_area_is_not_empty() -> None:
    class RetryOnFocusAreaClient(FakeOpenAIClient):
        def __init__(self) -> None:
            super().__init__()
            self.person_attempts = 0

        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                self.person_attempts += 1
                if self.person_attempts == 1:
                    return json.dumps(
                        {
                            "focus_area": ["immunotherapy"],
                            "big_questions": [
                                {
                                    "question": "How do we robustly validate signatures?",
                                    "why_important": "Avoids false biomarker claims.",
                                    "related_papers": ["papers/test-paper"],
                                }
                            ],
                        }
                    )
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

    client = RetryOnFocusAreaClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    cards = adapter.derive_person_cards(
        [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
    )

    assert cards[0]["big_questions"][0]["question"] == "How do we robustly validate signatures?"
    assert cards[0]["focus_area"] == []
    assert client.person_attempts == 2


def test_openai_summary_adapter_raises_when_person_focus_area_is_not_empty_after_retries() -> None:
    class NonEmptyFocusAreaClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return json.dumps(
                    {
                        "focus_area": ["immunotherapy"],
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

    client = NonEmptyFocusAreaClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    with pytest.raises(
        ValueError,
        match=r"person generation failed after 2 attempts.*focus_area must be present and equal to \[\]",
    ):
        adapter.derive_person_cards(
            [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
        )


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

    assert len(
        [call for call in client.summary_calls if call["text"].startswith("Generate person card JSON")]
    ) == 2


def test_openai_summary_adapter_person_generation_prompt_includes_senior_professor_role_and_long_horizon_rubric() -> None:
    class PersonPromptClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
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

    client = PersonPromptClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    adapter.derive_person_cards(
        [{"slug": "papers/test-paper", "title": "T", "summary": "S", "corresponding_authors": ["a@b.org"]}]
    )

    prompt = next(call["text"] for call in client.summary_calls if call["text"].startswith("Generate person card JSON"))
    assert "senior professor" in prompt
    assert "long-horizon" in prompt
    assert "no fabricated papers" in prompt


def test_openai_summary_adapter_person_generation_error_contains_person_slug_context() -> None:
    class AlwaysInvalidPersonClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate person card JSON"):
                return '{"focus_area": [], "big_questions": []}'
            return "{}"

    client = AlwaysInvalidPersonClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    with pytest.raises(
        ValueError,
        match=r"person generation failed after 2 attempts.*people/a-b-org",
    ):
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
            "focus_area": [],
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
    assert len(client.summary_calls) == 4
    assert client.summary_calls[0]["text"].startswith("Extract bibliographic metadata from the first-page OCR/text")
    assert client.summary_calls[1]["text"].startswith("Create a concise structured summary of the paper")
    assert "logical flow of sections and experiments" in client.summary_calls[1]["text"]
    assert "bullet points for key results with figure references" in client.summary_calls[1]["text"]
    assert client.summary_calls[2]["text"].startswith("Generate person card JSON")
    assert client.summary_calls[3]["text"].startswith("Generate topic card JSON")


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
    prompt = client.summary_calls[0]["text"]
    assert prompt.startswith("Extract bibliographic metadata from the first-page OCR/text")
    assert "Role: You are a precise scientific metadata extraction assistant." in prompt
    assert "Objective: Extract bibliographic metadata from first-page OCR text." in prompt
    assert "Evidence boundary: Use only the text provided below; do not use outside knowledge." in prompt
    assert "Output contract: Return strict JSON object only with keys authors (array of strings), journal (string), year (integer)." in prompt
    assert "Defaults/failure policy: If unknown, use authors=[], journal=\"\", year=0." in prompt
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
    fallback_prompt = client.summary_calls[2]["text"]
    assert fallback_prompt.startswith("Extract corresponding author email addresses")
    assert "Role: You are an extraction assistant for author contact metadata." in fallback_prompt
    assert "Output contract: Return strict JSON array only, no prose." in fallback_prompt
    assert "Evidence boundary: Use only the provided first-page text." in fallback_prompt


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


def test_openai_summary_adapter_generates_topics_from_all_person_big_questions_via_llm() -> None:
    # Red-phase test.
    class TopicLLMClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/gut-microbiome-and-lung-cancer-treatment",
                            "type": "topic",
                            "topic": "gut microbiome and lung cancer treatment",
                            "related_big_questions": [
                                {
                                    "question": "How can gut microbiome signals improve lung cancer treatment response?",
                                    "why_important": "Could personalize treatment and improve outcomes.",
                                    "related_papers": ["papers/a"],
                                    "related_people": ["people/alice-example-org"],
                                },
                                {
                                    "question": "How does lung microbiome composition affect lung infection severity?",
                                    "why_important": "May enable earlier intervention for respiratory disease.",
                                    "related_papers": ["papers/b"],
                                    "related_people": ["people/bob-example-org"],
                                },
                            ],
                            "related_people": ["people/alice-example-org", "people/bob-example-org"],
                            "related_papers": ["papers/a", "papers/b"],
                        }
                    ]
                )
            return "{}"

    client = TopicLLMClient()
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

    topic_generation_calls = [
        call for call in client.summary_calls if call["text"].startswith("Generate topic card JSON")
    ]
    assert len(topic_generation_calls) == 1
    assert "people/alice-example-org" in topic_generation_calls[0]["text"]
    assert "people/bob-example-org" in topic_generation_calls[0]["text"]
    assert "How can gut microbiome signals improve lung cancer treatment response?" in topic_generation_calls[0]["text"]
    assert "How does lung microbiome composition affect lung infection severity?" in topic_generation_calls[0]["text"]
    assert topic_cards == [
        {
            "slug": "topics/gut-microbiome-and-lung-cancer-treatment",
            "type": "topic",
            "topic": "gut microbiome and lung cancer treatment",
            "related_big_questions": [
                {
                    "question": "How can gut microbiome signals improve lung cancer treatment response?",
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/a"],
                    "related_people": ["people/alice-example-org"],
                },
                {
                    "question": "How does lung microbiome composition affect lung infection severity?",
                    "why_important": "May enable earlier intervention for respiratory disease.",
                    "related_papers": ["papers/b"],
                    "related_people": ["people/bob-example-org"],
                },
            ],
            "related_people": ["people/alice-example-org", "people/bob-example-org"],
            "related_papers": ["papers/a", "papers/b"],
        }
    ]


def test_openai_summary_adapter_topic_generation_prompt_includes_senior_professor_role_and_conceptual_coherence_rubric() -> None:
    class TopicPromptClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/x",
                            "type": "topic",
                            "topic": "x",
                            "related_big_questions": [
                                {
                                    "question": "Q",
                                    "why_important": "W",
                                    "related_people": ["people/a"],
                                    "related_papers": ["papers/a"],
                                }
                            ],
                            "related_people": ["people/a"],
                            "related_papers": ["papers/a"],
                        }
                    ]
                )
            return "{}"

    client = TopicPromptClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    adapter.derive_topic_cards(
        [
            {
                "slug": "people/a",
                "type": "person",
                "focus_area": [],
                "big_questions": [
                    {
                        "question": "Q",
                        "why_important": "W",
                        "related_papers": ["papers/a"],
                    }
                ],
                "related_papers": ["papers/a"],
            }
        ]
    )

    prompt = next(call["text"] for call in client.summary_calls if call["text"].startswith("Generate topic card JSON"))
    assert "senior professor" in prompt
    assert "maximize conceptual coherence" in prompt
    assert "strict JSON array only" in prompt


def test_openai_summary_adapter_rejects_empty_topic_payload_array() -> None:
    class EmptyTopicArrayClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return "[]"
            return "{}"

    client = EmptyTopicArrayClient()
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
        }
    ]

    with pytest.raises(ValueError, match=r"topic generation failed after 2 attempts: empty topic payload"):
        adapter.derive_topic_cards(person_cards)


def test_openai_summary_adapter_rejects_topic_with_empty_top_level_related_lists() -> None:
    class EmptyTopLevelRelationsClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/gut-microbiome-and-lung-cancer-treatment",
                            "type": "topic",
                            "topic": "gut microbiome and lung cancer treatment",
                            "related_big_questions": [
                                {
                                    "question": "How can gut microbiome signals improve lung cancer treatment response?",
                                    "why_important": "Could personalize treatment and improve outcomes.",
                                    "related_papers": ["papers/a"],
                                    "related_people": ["people/alice-example-org"],
                                }
                            ],
                            "related_people": [],
                            "related_papers": [],
                        }
                    ]
                )
            return "{}"

    client = EmptyTopLevelRelationsClient()
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
        }
    ]

    with pytest.raises(
        ValueError,
        match=r"topic generation failed after 2 attempts: topic entry must have non-empty related_people and related_papers",
    ):
        adapter.derive_topic_cards(person_cards)


def test_openai_summary_adapter_retries_topic_generation_once_then_raises() -> None:
    # Red-phase test.
    class RetryTopicClient(FakeOpenAIClient):
        def __init__(self) -> None:
            super().__init__()
            self.topic_attempts = 0

        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                self.topic_attempts += 1
                return json.dumps(
                    [
                        {
                            "slug": "topics/x",
                            "type": "topic",
                            "topic": "x",
                            "related_big_questions": [],
                        }
                    ]
                )
            return "{}"

    client = RetryTopicClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")

    with pytest.raises(ValueError, match=r"topic generation failed after 2 attempts"):
        adapter.derive_topic_cards(
            [
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
                }
            ]
        )

    assert client.topic_attempts == 2


def test_openai_summary_adapter_allows_topic_question_with_provenance_consistent_non_cartesian_association() -> None:
    class NonCartesianAssociationClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/microbiome-and-treatment-response",
                            "type": "topic",
                            "topic": "microbiome and treatment response",
                            "related_big_questions": [
                                {
                                    "question": "How can microbiome signals improve treatment response?",
                                    "why_important": "Could personalize treatment and improve outcomes.",
                                    "related_papers": ["papers/a", "papers/b"],
                                    "related_people": ["people/alice-example-org", "people/bob-example-org"],
                                }
                            ],
                            "related_people": ["people/alice-example-org", "people/bob-example-org"],
                            "related_papers": ["papers/a", "papers/b"],
                        }
                    ]
                )
            return "{}"

    client = NonCartesianAssociationClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    person_cards = [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": "How can microbiome signals improve treatment response?",
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
                    "question": "How can microbiome signals improve treatment response?",
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/b"],
                }
            ],
            "related_papers": ["papers/b"],
        },
    ]

    assert adapter.derive_topic_cards(person_cards) == [
        {
            "slug": "topics/microbiome-and-treatment-response",
            "type": "topic",
            "topic": "microbiome and treatment response",
            "related_big_questions": [
                {
                    "question": "How can microbiome signals improve treatment response?",
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/a", "papers/b"],
                    "related_people": ["people/alice-example-org", "people/bob-example-org"],
                }
            ],
            "related_people": ["people/alice-example-org", "people/bob-example-org"],
            "related_papers": ["papers/a", "papers/b"],
        }
    ]


def test_openai_summary_adapter_rejects_topic_question_with_mismatched_person_paper_association() -> None:
    class MismatchedQuestionAssociationClient(FakeOpenAIClient):
        def summarize(self, text: str, model: str) -> str:  # noqa: ARG002
            self.summary_calls.append({"text": text, "model": model})
            if text.startswith("Generate topic card JSON"):
                return json.dumps(
                    [
                        {
                            "slug": "topics/microbiome-and-treatment-response",
                            "type": "topic",
                            "topic": "microbiome and treatment response",
                            "related_big_questions": [
                                {
                                    "question": "How can microbiome signals improve treatment response?",
                                    "why_important": "Could personalize treatment and improve outcomes.",
                                    "related_papers": ["papers/b"],
                                    "related_people": ["people/alice-example-org"],
                                }
                            ],
                            "related_people": ["people/alice-example-org"],
                            "related_papers": ["papers/b"],
                        }
                    ]
                )
            return "{}"

    client = MismatchedQuestionAssociationClient()
    adapter = OpenAISummaryAdapter(client=client, model="gpt-4.1-mini")
    person_cards = [
        {
            "slug": "people/alice-example-org",
            "type": "person",
            "focus_area": [],
            "big_questions": [
                {
                    "question": "How can microbiome signals improve treatment response?",
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
                    "question": "How can microbiome signals improve treatment response?",
                    "why_important": "Could personalize treatment and improve outcomes.",
                    "related_papers": ["papers/b"],
                }
            ],
            "related_papers": ["papers/b"],
        },
    ]

    with pytest.raises(
        ValueError,
        match=r"topic generation failed after 2 attempts: related_big_questions person/paper associations must match source big-question links",
    ):
        adapter.derive_topic_cards(person_cards)

def test_deterministic_adapter_person_cards_include_focus_and_big_questions_contract() -> None:
    adapter = DeterministicLLMAdapter()

    person_cards = adapter.derive_person_cards(
        [
            {
                "slug": "papers/test-paper",
                "title": "Test Paper",
                "summary": "Key question solved: How does this method work?",
                "corresponding_authors": ["Alice Example <alice@example.org>"],
            }
        ]
    )

    assert person_cards[0]["slug"] == "people/alice-example-org"
    assert person_cards[0]["focus_area"]
    assert all(isinstance(area, str) and area.strip() for area in person_cards[0]["focus_area"])
    assert person_cards[0]["big_questions"]
    assert person_cards[0]["big_questions"][0]["question"].strip()
    assert person_cards[0]["big_questions"][0]["why_important"].strip()
    assert person_cards[0]["big_questions"][0]["related_papers"] == ["papers/test-paper"]
