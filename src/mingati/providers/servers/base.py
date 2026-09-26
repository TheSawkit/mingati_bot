from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ServerStatus:
    online: bool
    players_online: int = 0
    players_max: int = 0
    version: str | None = None
    latency_ms: int | None = None
    motd: str | None = None


OFFLINE = ServerStatus(online=False)


class ServerProvider(Protocol):
    kind: str
    label: str
    default_port: int

    async def status(self, address: str) -> ServerStatus: ...
