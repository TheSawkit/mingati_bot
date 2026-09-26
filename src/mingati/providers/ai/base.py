from dataclasses import dataclass
from typing import Literal, Protocol

import aiohttp

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class AIProvider(Protocol):
    name: str
    model: str

    async def complete(
        self, http: aiohttp.ClientSession, messages: list[ChatMessage], max_tokens: int
    ) -> str: ...
