import asyncio
import re
from dataclasses import dataclass

import aiosqlite

from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.providers.servers import ServerProvider, ServerStatus
from mingati.utils.text import clean_text

MAX_SERVERS = 10
MAX_NAME_LENGTH = 32
ADDRESS_PATTERN = re.compile(r"^[A-Za-z0-9.-]{1,253}(:\d{1,5})?$")


@dataclass(frozen=True, slots=True)
class GameServer:
    name: str
    kind: str
    address: str


def validate_address(raw: str) -> str:
    address = raw.strip().lower()
    port = address.rpartition(":")[2] if ":" in address else None
    if not ADDRESS_PATTERN.match(address) or (port is not None and not 0 < int(port) < 65536):
        raise UserFacingError("Adresse invalide. Exemples : `mc.exemple.fr`, `192.168.1.20:25565`.")
    return address


class GameServerService:
    """Game servers followed by the guild and their live status, whatever the game."""

    def __init__(self, database: Database, providers: dict[str, ServerProvider]) -> None:
        self.database = database
        self.providers = providers

    async def add(self, guild_id: int, name: str, kind: str, address: str) -> GameServer:
        name = clean_text(name)
        if not name or len(name) > MAX_NAME_LENGTH:
            raise UserFacingError(f"Le nom doit faire entre 1 et {MAX_NAME_LENGTH} caractères.")
        if kind not in self.providers:
            raise UserFacingError("Type de serveur non pris en charge.")
        server = GameServer(name, kind, validate_address(address))
        if len(await self.list_servers(guild_id)) >= MAX_SERVERS:
            raise UserFacingError(f"Maximum {MAX_SERVERS} serveurs.")
        try:
            await self.database.execute(
                "INSERT INTO game_servers (guild_id, name, kind, address) VALUES (?, ?, ?, ?)",
                (guild_id, server.name, server.kind, server.address),
            )
        except aiosqlite.IntegrityError as error:
            raise UserFacingError(f"Un serveur « {name} » existe déjà.") from error
        return server

    async def remove(self, guild_id: int, name: str) -> None:
        removed = await self.database.execute(
            "DELETE FROM game_servers WHERE guild_id = ? AND name = ?", (guild_id, clean_text(name))
        )
        if not removed:
            raise UserFacingError(f"Aucun serveur « {name} ».")

    async def list_servers(self, guild_id: int) -> list[GameServer]:
        rows = await self.database.fetch_all(
            "SELECT name, kind, address FROM game_servers WHERE guild_id = ? ORDER BY name",
            (guild_id,),
        )
        return [GameServer(row["name"], row["kind"], row["address"]) for row in rows]

    async def statuses(
        self, guild_id: int, name: str | None = None
    ) -> list[tuple[GameServer, ServerStatus]]:
        """Query every (or one) server concurrently; an unreachable server is reported offline."""
        servers = await self.list_servers(guild_id)
        if name is not None:
            servers = [server for server in servers if server.name.casefold() == name.casefold()]
            if not servers:
                raise UserFacingError(f"Aucun serveur « {name} ».")
        results = await asyncio.gather(
            *(self.providers[server.kind].status(server.address) for server in servers)
        )
        return list(zip(servers, results, strict=True))
