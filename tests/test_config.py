from pathlib import Path

import pytest
from pydantic import ValidationError

from mingati.config import Settings


def test_loads_ids_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("DISCORD_GUILD_ID", "933379075270119484")
    monkeypatch.setenv("CHANNEL_CREATE_VOICE_GAMING_ID", "1337126878112383058")

    settings = Settings()

    assert settings.discord_guild_id == 933379075270119484
    assert settings.channel_create_voice_gaming_id == 1337126878112383058
    assert settings.database_path == Path("data/mingati.db")


def test_empty_optional_values_are_treated_as_unset(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "DISCORD_TOKEN=abc\nDISCORD_GUILD_ID=1\nCHANNEL_CHAT_ID=\nGEMINI_API_KEY=\n"
    )

    settings = Settings()

    assert settings.channel_chat_id is None
    assert settings.gemini_api_key is None


def test_missing_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_GUILD_ID", "1")

    with pytest.raises(ValidationError, match="discord_token"):
        Settings()


def test_non_numeric_id_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("DISCORD_GUILD_ID", "mingati")

    with pytest.raises(ValidationError, match="discord_guild_id"):
        Settings()


def test_secrets_never_appear_in_repr() -> None:
    settings = Settings(discord_token="super-secret", discord_guild_id=1, gemini_api_key="key-123")

    assert "super-secret" not in repr(settings)
    assert "key-123" not in repr(settings)


def test_staff_role_ids_ignore_unset_roles() -> None:
    settings = Settings(discord_token="t", discord_guild_id=1, role_moderator_id=42)

    assert settings.staff_role_ids == frozenset({42})


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Settings(discord_token="t", discord_guild_id=1, timezone="Mars/Olympus")


def test_timezone_defaults_to_brussels() -> None:
    settings = Settings(discord_token="t", discord_guild_id=1)

    assert settings.timezone.key == "Europe/Brussels"


def test_timezone_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Europe/Paris")

    settings = Settings(discord_token="t", discord_guild_id=1)

    assert settings.timezone.key == "Europe/Paris"
