from typing import Any


class GeminiClient:
    def __init__(self, api_key: str, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            from google import genai

            sdk_client = genai.Client(api_key=api_key)
        self.sdk_client = sdk_client

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.models.generate_content(model=model, contents=text)
        return response.text.strip()
