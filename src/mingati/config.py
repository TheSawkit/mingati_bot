from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and the optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    discord_token: SecretStr
    discord_guild_id: int

    channel_chat_id: int | None = None
    channel_gaming_id: int | None = None
    channel_who_plays_id: int | None = None
    channel_free_games_id: int | None = None

    channel_create_voice_general_id: int | None = None
    channel_create_voice_gaming_id: int | None = None

    role_staff_id: int | None = None
    role_moderator_id: int | None = None

    llm_provider: Literal["gemini"] = "gemini"
    llm_model: str = ""
    gemini_api_key: SecretStr | None = None

    database_path: Path = Path("data/mingati.db")
    log_level: LogLevel = "INFO"
    timezone: ZoneInfo = ZoneInfo("Europe/Brussels")
    store_country: str = "BE"

    @property
    def voice_trigger_ids(self) -> frozenset[int]:
        """Channels that spawn a temporary voice room when someone joins them."""
        return frozenset(
            channel_id
            for channel_id in (
                self.channel_create_voice_general_id,
                self.channel_create_voice_gaming_id,
            )
            if channel_id
        )

    @property
    def staff_role_ids(self) -> frozenset[int]:
        """Role IDs allowed to run staff-only commands."""
        return frozenset(
            role_id for role_id in (self.role_staff_id, self.role_moderator_id) if role_id
        )
