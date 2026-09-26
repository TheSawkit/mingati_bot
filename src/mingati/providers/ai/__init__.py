import logging

from mingati.config import Settings
from mingati.providers.ai.base import AIProvider, ChatMessage
from mingati.providers.ai.openai_compatible import OpenAICompatibleProvider

__all__ = ["AIProvider", "ChatMessage", "create_ai_provider"]

log = logging.getLogger(__name__)

BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
}


def create_ai_provider(settings: Settings) -> AIProvider | None:
    """Provider selected by LLM_PROVIDER, or None when its key or LLM_MODEL is missing."""
    api_key = {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}[
        settings.llm_provider
    ]
    if api_key is None or not settings.llm_model:
        log.warning("AI disabled: set LLM_MODEL and the API key of LLM_PROVIDER")
        return None
    return OpenAICompatibleProvider(
        settings.llm_provider, BASE_URLS[settings.llm_provider], api_key, settings.llm_model
    )
