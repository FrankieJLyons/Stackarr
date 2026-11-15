import httpx
import pytest

from stackarr.config import Integration
from stackarr.integrations import IntegrationError, collect


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [(200, "Ok."), (204, "")])
async def test_old_and_current_login_contract(status, body):
    def respond(request):
        if request.url.path.endswith("/login"):
            return httpx.Response(status, text=body, headers={"set-cookie": "SID_28080=synthetic; Path=/"})
        assert "SID_28080=synthetic" in request.headers["cookie"]
        return httpx.Response(200, json=[])

    result = await collect("qbittorrent", Integration(url="http://qbit.example:28080"),
                           {"username": "test", "password": "synthetic"}, httpx.MockTransport(respond))
    assert result == {"downloads": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [(200, "Fails."), (401, ""), (403, ""), (302, "")])
async def test_failed_login_never_reads_downloads(status, body):
    def respond(request):
        assert request.url.path.endswith("/login")
        return httpx.Response(status, text=body)

    with pytest.raises(IntegrationError) as error:
        await collect("qbittorrent", Integration(url="http://qbit.example"), {}, httpx.MockTransport(respond))
    assert error.value.code == "authentication"


@pytest.mark.asyncio
async def test_empty_login_response_does_not_hide_protected_endpoint_failure():
    def respond(request):
        return httpx.Response(204 if request.url.path.endswith("/login") else 401)

    with pytest.raises(IntegrationError) as error:
        await collect("qbittorrent", Integration(url="http://qbit.example"), {}, httpx.MockTransport(respond))
    assert error.value.code == "authentication"
