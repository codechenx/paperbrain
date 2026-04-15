from typing import Any


class OllamaCloudClient:
    def __init__(
        self, api_key: str, base_url: str, sdk_client: Any | None = None
    ) -> None:
        if sdk_client is None:
            import ollama

            client_kwargs: dict[str, Any] = {"host": base_url}
            if api_key:
                client_kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
            sdk_client = ollama.Client(**client_kwargs)
        self.sdk_client = sdk_client

    def summarize(self, text: str, model: str) -> str:
        response = self.sdk_client.chat(
            model=model, messages=[{"role": "user", "content": text}]
        )
        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
        if content is None:
            return ""
        return content.strip()
