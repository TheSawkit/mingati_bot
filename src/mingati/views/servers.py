import discord

from mingati.providers.servers import ServerStatus
from mingati.services.game_servers import GameServer


def describe_status(status: ServerStatus) -> str:
    if not status.online:
        return "🔴 Hors ligne"
    lines = [f"🟢 En ligne · 👥 {status.players_online}/{status.players_max}"]
    details = [status.version] if status.version else []
    if status.latency_ms is not None:
        details.append(f"{status.latency_ms} ms")
    if details:
        lines.append(" · ".join(details))
    if status.motd:
        lines.append(f"*{status.motd[:100]}*")
    return "\n".join(lines)


def build_servers_embed(results: list[tuple[GameServer, ServerStatus]]) -> discord.Embed:
    """One field per server: online state, players, version and latency."""
    embed = discord.Embed(title="🖥️ Serveurs de jeux", color=discord.Color.green())
    if not results:
        embed.description = "Aucun serveur configuré. Le staff peut en ajouter avec `/server add`."
    for server, status in results:
        embed.add_field(
            name=f"{server.name} — `{server.address}`", value=describe_status(status), inline=False
        )
    return embed
