import pytest
from aiohttp import ClientResponseError, web
from aiohttp.test_utils import TestServer

from mingati.providers import http
from mingati.providers.http import ProviderError, create_http_session, fetch_json


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "RETRY_DELAYS_SECONDS", (0, 0))


async def serve(statuses: list[int]):
    calls: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        calls.append(request.query_string)
        status = statuses[min(len(calls), len(statuses)) - 1]
        return web.json_response({"ok": True}, status=status)

    app = web.Application()
    app.router.add_get("/", handler)
    server = TestServer(app)
    await server.start_server()
    return server, calls


async def test_retries_server_errors_then_succeeds() -> None:
    server, calls = await serve([503, 200])
    async with create_http_session() as session:
        assert await fetch_json(session, str(server.make_url("/")), {"a": "1"}) == {"ok": True}
    await server.close()

    assert calls == ["a=1", "a=1"]


async def test_gives_up_after_the_last_retry() -> None:
    server, calls = await serve([500])
    async with create_http_session() as session:
        with pytest.raises(ProviderError, match="unreachable"):
            await fetch_json(session, str(server.make_url("/")))
    await server.close()

    assert len(calls) == 3


async def test_client_errors_are_not_retried() -> None:
    server, calls = await serve([404])
    async with create_http_session() as session:
        with pytest.raises(ClientResponseError):
            await fetch_json(session, str(server.make_url("/")))
    await server.close()

    assert len(calls) == 1
