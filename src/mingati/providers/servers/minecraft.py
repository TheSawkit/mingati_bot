import logging

from dns.exception import DNSException
from mcstatus import JavaServer

from mingati.providers.servers.base import OFFLINE, ServerStatus

log = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 5
UNREACHABLE_ERRORS = (OSError, TimeoutError, ValueError, DNSException)


class MinecraftJavaProvider:
    """Minecraft Java Edition status through the Server List Ping protocol (mcstatus)."""

    kind = "minecraft"
    label = "Minecraft Java"
    default_port = JavaServer.DEFAULT_PORT

    async def status(self, address: str) -> ServerStatus:
        try:
            server = await JavaServer.async_lookup(address, timeout=LOOKUP_TIMEOUT_SECONDS)
            response = await server.async_status(tries=1)
        except UNREACHABLE_ERRORS as error:
            log.info("Minecraft server %s unreachable: %s", address, error)
            return OFFLINE
        return ServerStatus(
            online=True,
            players_online=response.players.online,
            players_max=response.players.max,
            version=response.version.name,
            latency_ms=round(response.latency),
            motd=response.motd.to_plain().strip() or None,
        )
