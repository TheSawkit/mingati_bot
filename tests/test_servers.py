from dataclasses import dataclass, field

import pytest
from mcstatus import JavaServer

from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.providers.servers import OFFLINE, ServerStatus
from mingati.providers.servers.minecraft import MinecraftJavaProvider
from mingati.services.game_servers import MAX_SERVERS, GameServerService, validate_address
from mingati.views.servers import build_servers_embed, describe_status

GUILD = 1
ONLINE = ServerStatus(True, 3, 20, "1.21.4", 42, "Bienvenue sur Mingati")


@dataclass
class FakeProvider:
    kind: str = "minecraft"
    label: str = "Minecraft Java"
    default_port: int = 25565
    statuses: dict[str, ServerStatus] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def status(self, address: str) -> ServerStatus:
        self.asked.append(address)
        return self.statuses.get(address, OFFLINE)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(statuses={"mc.mingati.fr": ONLINE})


@pytest.fixture
def service(database: Database, provider: FakeProvider) -> GameServerService:
    return GameServerService(database, {"minecraft": provider})


async def test_servers_are_added_listed_and_queried(service, provider) -> None:
    await service.add(GUILD, "Survie", "minecraft", " MC.Mingati.fr ")
    await service.add(GUILD, "Créatif", "minecraft", "10.0.0.5:25566")

    results = await service.statuses(GUILD)

    assert [(server.name, status.online) for server, status in results] == [
        ("Créatif", False),
        ("Survie", True),
    ]
    assert sorted(provider.asked) == ["10.0.0.5:25566", "mc.mingati.fr"]


async def test_one_server_can_be_queried_by_name_case_insensitively(service) -> None:
    await service.add(GUILD, "Survie", "minecraft", "mc.mingati.fr")

    [(server, status)] = await service.statuses(GUILD, "survie")

    assert server.name == "Survie" and status == ONLINE
    with pytest.raises(UserFacingError, match="Aucun serveur"):
        await service.statuses(GUILD, "inconnu")


async def test_names_are_unique_per_guild(service) -> None:
    await service.add(GUILD, "Survie", "minecraft", "a.fr")

    with pytest.raises(UserFacingError, match="existe déjà"):
        await service.add(GUILD, "survie", "minecraft", "b.fr")
    await service.add(GUILD + 1, "Survie", "minecraft", "a.fr")


async def test_remove_and_limits(service) -> None:
    with pytest.raises(UserFacingError, match="Aucun serveur"):
        await service.remove(GUILD, "Survie")
    for index in range(MAX_SERVERS):
        await service.add(GUILD, f"S{index}", "minecraft", "a.fr")
    with pytest.raises(UserFacingError, match="Maximum"):
        await service.add(GUILD, "Trop", "minecraft", "a.fr")
    with pytest.raises(UserFacingError, match="non pris en charge"):
        await service.add(GUILD + 1, "X", "terraria", "a.fr")

    await service.remove(GUILD, "S0")
    assert len(await service.list_servers(GUILD)) == MAX_SERVERS - 1


@pytest.mark.parametrize(
    "address", ["", "mc fr", "a.fr:0", "a.fr:70000", "a.fr:abc", "http://a.fr"]
)
def test_invalid_addresses_are_refused(address: str) -> None:
    with pytest.raises(UserFacingError, match="Adresse invalide"):
        validate_address(address)


async def test_unreachable_minecraft_server_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(address: str, **options: float) -> JavaServer:
        raise ConnectionRefusedError

    monkeypatch.setattr(JavaServer, "async_lookup", refuse)

    assert await MinecraftJavaProvider().status("mc.mingati.fr") == OFFLINE


def test_status_display() -> None:
    assert describe_status(OFFLINE) == "🔴 Hors ligne"
    assert describe_status(ONLINE).splitlines() == [
        "🟢 En ligne · 👥 3/20",
        "1.21.4 · 42 ms",
        "*Bienvenue sur Mingati*",
    ]
    assert "/server add" in build_servers_embed([]).description
