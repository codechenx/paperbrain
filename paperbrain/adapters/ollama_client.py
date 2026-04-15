from typing import Any


class OllamaCloudClient:
    def __init__(
        self, api_key: str, base_url: str, sdk_client: Any | None = None
    ) -> None:
        if sdk_client is None:
            import ollama

            normalized_api_key = api_key.strip()
            headers = (
                {"Authorization": f"Bearer {normalized_api_key}"}
                if normalized_api_key
                else None
            )
            sdk_client = ollama.Client(host=base_url, headers=headers)
        self.sdk_client = sdk_client

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.chat(
            model=model, messages=[{"role": "user", "content": text}]
        )
        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
        if content is None:
            return ""
        return str(content).strip()
