from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from mingati.config import Settings
from mingati.errors import UserFacingError
from mingati.providers.ai import ChatMessage, create_ai_provider
from mingati.providers.ai.openai_compatible import OpenAICompatibleProvider, parse_completion
from mingati.providers.http import ProviderError
from mingati.providers.jokes import Joke, create_joke_provider, parse_blague
from mingati.services.billy import (
    BILLY_PERSONA,
    FALLBACK_REPLY,
    JOKE_FALLBACKS,
    MAX_REPLY_LENGTH,
    BillyService,
    UsageLimiter,
)

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)
HTTP = object()


@dataclass
class FakeAI:
    replies: list[str | Exception] = field(default_factory=list)
    prompts: list[list[ChatMessage]] = field(default_factory=list)
    name: str = "fake"
    model: str = "fake-1"

    async def complete(self, http, messages, max_tokens) -> str:
        self.prompts.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@dataclass
class FakeJokes:
    result: Joke | Exception

    async def random(self, http) -> Joke:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_limiter_enforces_a_per_member_cooldown() -> None:
    limiter = UsageLimiter(cooldown=timedelta(seconds=20), daily_limit=10)
    limiter.acquire(1, NOW)

    with pytest.raises(UserFacingError, match="20 s"):
        limiter.acquire(1, NOW)
    limiter.acquire(2, NOW)
    limiter.acquire(1, NOW + timedelta(seconds=21))


def test_limiter_caps_daily_usage_and_resets_the_next_day() -> None:
    limiter = UsageLimiter(cooldown=timedelta(0), daily_limit=2)
    limiter.acquire(1, NOW)
    limiter.acquire(2, NOW)

    with pytest.raises(UserFacingError, match="demain"):
        limiter.acquire(3, NOW)
    limiter.acquire(3, NOW + timedelta(days=1))


async def test_answer_uses_the_persona_and_trims_long_replies() -> None:
    ai = FakeAI(replies=["x" * 5000])
    billy = BillyService(ai, None)

    question = billy.prepare_question(1, "  Ça   va ? ", NOW)
    reply = await billy.answer(HTTP, question, "Tom")

    assert question == "Ça va ?"
    assert len(reply) == MAX_REPLY_LENGTH
    assert ai.prompts[0][0] == ChatMessage("system", BILLY_PERSONA)
    assert ai.prompts[0][1] == ChatMessage("user", "Tom : Ça va ?")


async def test_answer_falls_back_in_character_when_the_ai_fails() -> None:
    billy = BillyService(FakeAI(replies=[ProviderError("429")]), None)

    assert await billy.answer(HTTP, "salut", "Tom") == FALLBACK_REPLY


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_invalid_questions_are_refused(question: str) -> None:
    with pytest.raises(UserFacingError):
        BillyService(FakeAI(), None).prepare_question(1, question, NOW)


def test_questions_are_refused_when_no_ai_is_configured() -> None:
    with pytest.raises(UserFacingError, match="pas configurée"):
        BillyService(None, None).prepare_question(1, "salut", NOW)


async def test_joke_prefers_blagues_api() -> None:
    joke = Joke("Question ?", "Chute.")

    assert await BillyService(FakeAI(), FakeJokes(joke)).joke(HTTP) == joke


async def test_joke_falls_back_to_ai_then_builtin_list() -> None:
    from_ai = BillyService(FakeAI(replies=["Pourquoi ?\nParce que."]), FakeJokes(ProviderError()))
    assert await from_ai.joke(HTTP) == Joke("Pourquoi ?", "Parce que.")

    offline = BillyService(FakeAI(replies=[ProviderError()]), FakeJokes(ProviderError()))
    assert await offline.joke(HTTP) in JOKE_FALLBACKS


async def test_welcome_mentions_the_member_even_without_ai() -> None:
    with_ai = BillyService(FakeAI(replies=["Oh non, un nouveau..."]), None)
    assert await with_ai.welcome(HTTP, "<@7>", "Zoé") == "<@7> Oh non, un nouveau..."

    offline = await BillyService(None, None).welcome(HTTP, "<@7>", "Zoé")
    assert "<@7>" in offline


def test_parse_completion() -> None:
    assert parse_completion({"choices": [{"message": {"content": " hey "}}]}) == "hey"
    for bad in ({}, {"choices": []}, {"choices": [{"message": {"content": "  "}}]}):
        with pytest.raises(ProviderError):
            parse_completion(bad)


def test_parse_blague() -> None:
    payload = {"id": 1, "type": "dev", "joke": "Q ?", "answer": "R."}

    assert parse_blague(payload) == Joke("Q ?", "R.")
    with pytest.raises(ProviderError):
        parse_blague({"id": 1})


def test_ai_provider_follows_llm_provider_setting() -> None:
    base = {"discord_token": "t", "discord_guild_id": 1, "llm_model": "m"}

    assert create_ai_provider(Settings(**base)) is None
    gemini = create_ai_provider(Settings(**base, gemini_api_key="g"))
    groq = create_ai_provider(Settings(**base, llm_provider="groq", groq_api_key="k"))

    assert isinstance(gemini, OpenAICompatibleProvider) and gemini.name == "gemini"
    assert isinstance(groq, OpenAICompatibleProvider) and groq.name == "groq"
    assert create_ai_provider(Settings(**{**base, "llm_model": ""}, gemini_api_key="g")) is None


def test_joke_provider_needs_a_token() -> None:
    settings = Settings(discord_token="t", discord_guild_id=1)

    assert create_joke_provider(settings) is None
    assert create_joke_provider(settings.model_copy(update={"blagues_api_token": SecretStr("x")}))


async def test_ai_joke_keeps_the_last_two_lines_when_billy_adds_a_remark() -> None:
    billy = BillyService(
        FakeAI(replies=["ouais ok frr\n\nPourquoi les poissons ?\nParce que."]), None
    )

    assert await billy.joke(HTTP) == Joke("Pourquoi les poissons ?", "Parce que.")
