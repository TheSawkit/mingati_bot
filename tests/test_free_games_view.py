from datetime import UTC, datetime

import discord

from mingati.providers.games import FreeGame
from mingati.views.free_games import build_announcement, find_logo, platform_style

ENDS = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


class FakeEmoji:
    def __init__(self, name: str, emoji_id: int) -> None:
        self.name = name
        self.id = emoji_id
        self.url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"

    def __str__(self) -> str:
        return f"<:{self.name}:{self.id}>"


GOG_ID, EPIC_ID, STEAM_ID = 1447059257211224155, 1447060063553585152, 1447055808893419583
SERVER_EMOJIS = [
    FakeEmoji("gog", GOG_ID),
    FakeEmoji("epic_games", EPIC_ID),
    FakeEmoji("steam", STEAM_ID),
]


def epic_game(**overrides) -> FreeGame:
    options = {
        "source": "epic",
        "external_id": "42",
        "title": "Astrea Six Sided Oracles",
        "url": "https://store.epicgames.com/fr/p/astrea",
        "image_url": "https://cdn.epicgames.com/astrea.jpg",
        "ends_at": ENDS,
    } | overrides
    return FreeGame(**options)


def test_each_store_has_its_own_label_color_and_logo() -> None:
    styles = [platform_style(source) for source in ("epic", "steam", "gog")]

    assert [style.label for style in styles] == ["Epic Games", "Steam", "GOG"]
    assert len({style.color.value for style in styles}) == 3
    assert [style.emoji_name for style in styles] == ["epic_games", "steam", "gog"]


def test_logo_is_found_by_emoji_name_and_missing_ones_fall_back() -> None:
    assert str(find_logo(SERVER_EMOJIS, platform_style("steam"))) == f"<:steam:{STEAM_ID}>"
    assert find_logo([], platform_style("steam")) is None


async def test_announcement_uses_the_store_logo_everywhere() -> None:
    style = platform_style("epic")
    logo = find_logo(SERVER_EMOJIS, style)

    announcement = build_announcement(epic_game(), logo)
    embed = announcement.embed

    assert (
        announcement.content == f"<:epic_games:{EPIC_ID}> Nouveau jeu gratuit sur **Epic Games** !"
    )
    assert embed.author.name == "Epic Games"
    assert embed.author.icon_url == f"https://cdn.discordapp.com/emojis/{EPIC_ID}.png"
    assert embed.title == "Astrea Six Sided Oracles"
    assert embed.url == "https://store.epicgames.com/fr/p/astrea"
    assert embed.color == style.color
    assert embed.image.url == "https://cdn.epicgames.com/astrea.jpg"
    assert embed.fields[0].name == "⏳ Fin de l'offre"
    assert "<t:1790866800:F>" in embed.fields[0].value
    [button] = announcement.view.children
    assert isinstance(button, discord.ui.Button)
    assert button.style is discord.ButtonStyle.link
    assert button.url == "https://store.epicgames.com/fr/p/astrea"
    assert button.label == "Récupérer sur Epic Games"
    assert (button.emoji.name, button.emoji.id) == ("epic_games", EPIC_ID)


async def test_announcement_without_logo_or_end_date_stays_readable() -> None:
    announcement = build_announcement(
        epic_game(source="steam", ends_at=None, image_url=None), logo=None
    )

    assert announcement.content.startswith(platform_style("steam").fallback_emoji)
    assert announcement.embed.author.icon_url is None
    assert "non communiquée" in announcement.embed.fields[0].value
    assert announcement.embed.image.url is None


async def test_fallback_button_emoji_is_a_plain_unicode_emoji() -> None:
    [button] = build_announcement(epic_game(source="steam"), logo=None).view.children

    assert (button.emoji.name, button.emoji.id) == (platform_style("steam").fallback_emoji, None)
