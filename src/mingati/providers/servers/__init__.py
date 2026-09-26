from mingati.providers.servers.base import OFFLINE, ServerProvider, ServerStatus
from mingati.providers.servers.minecraft import MinecraftJavaProvider

__all__ = ["OFFLINE", "ServerProvider", "ServerStatus", "default_server_providers"]


def default_server_providers() -> dict[str, ServerProvider]:
    """Supported game server kinds, keyed by the value stored in game_servers.kind."""
    providers: list[ServerProvider] = [MinecraftJavaProvider()]
    return {provider.kind: provider for provider in providers}
