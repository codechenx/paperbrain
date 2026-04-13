from typing import Any

class OpenAIClient:
    def __init__(self, api_key: str, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            from openai import OpenAI

            sdk_client = OpenAI(api_key=api_key)
        self.sdk_client = sdk_client

    def embed(self, chunks: list[str], model: str) -> list[list[float]]:
        if not chunks:
            return []
        response = self.sdk_client.embeddings.create(model=model, input=chunks)
        return [item.embedding for item in response.data]

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.responses.create(model=model, input=text)
        return response.output_text
