from mingati.providers.games.base import FreeGame, GameProvider
from mingati.providers.games.epic import EpicProvider
from mingati.providers.games.gog import GogProvider
from mingati.providers.games.steam import SteamProvider

__all__ = ["FreeGame", "GameProvider", "default_game_providers"]


def default_game_providers(country: str) -> list[GameProvider]:
    """Every free games source Mingati follows, for the given store country."""
    return [EpicProvider(country), SteamProvider(country), GogProvider(country)]
