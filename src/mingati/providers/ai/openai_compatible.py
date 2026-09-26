from typing import Any

import aiohttp
from pydantic import SecretStr

from mingati.providers.ai.base import ChatMessage
from mingati.providers.http import ProviderError, request_json


def parse_completion(payload: dict[str, Any]) -> str:
    """Text of the first choice of a chat completion, or ProviderError when there is none."""
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderError("Unexpected chat completion payload") from error
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("Empty chat completion")
    return content.strip()


class OpenAICompatibleProvider:
    """Any chat completions API speaking the OpenAI format (Gemini, Groq, …)."""

    def __init__(self, name: str, base_url: str, api_key: SecretStr, model: str) -> None:
        self.name = name
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key

    async def complete(
        self, http: aiohttp.ClientSession, messages: list[ChatMessage], max_tokens: int
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        response = await request_json(http, "POST", self._url, payload=payload, headers=headers)
        return parse_completion(response)
