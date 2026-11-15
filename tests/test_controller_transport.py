import json
import secrets
import time

import httpx
import pytest

from stackarr.controller import InstallationController
from stackarr.controller_transport import (
    ControllerClient,
    ControllerConnectionError,
    create_controller_app,
    sign,
)
from stackarr.store import Store

KEY = bytes(range(32))  # Synthetic fixture only; enrollment must use random bytes.
ADDRESS = "http://127.0.0.1:28010"


@pytest.mark.asyncio
async def test_host_backup_review_uses_private_single_use_approval(rpc, monkeypatch):
    service, transport, _ = rpc
    from stackarr.host_recovery import HostBackups

    review = {"action": "host-backup", "name": "Whole-host recovery backup", "reviews": [{"apps": ["kuma"]}]}
    monkeypatch.setattr(HostBackups, "review", lambda self: review)
    client = ControllerClient(ADDRESS, KEY, transport)
    result = await client.request("host-backup-review")
    assert result["apps"] == ["Uptime Kuma"] and "Media" in result["notice"]
    queued = await client.request("managed-apply", {"review_reference": result["review_reference"]})
    assert service.deployments.actions.rows()[0]["id"] == queued["id"]
    with pytest.raises(ControllerConnectionError):
        await client.request("managed-apply", {"review_reference": result["review_reference"]})


@pytest.fixture
def rpc(tmp_path, monkeypatch):
    service = InstallationController(Store(tmp_path / "controller"), [], 28000)
    monkeypatch.setattr(service.deployments, "context", lambda: {"name": "fixture", "endpoint": "unix:///fixture"})
    monkeypatch.setattr("stackarr.deployment.preflight", lambda config: [{"check": "fixture", "ok": True}])
    calls = []
    from test_deployment import image_answer

    monkeypatch.setattr(service.deployments, "network_capacity", lambda *args: {"state": "available"})
    monkeypatch.setattr(service.deployments, "_call", lambda args, **kwargs: calls.append(args) or image_answer(args))
    monkeypatch.setattr("stackarr.seerr_storage.prepare", lambda *args: None)
    app = create_controller_app(service, KEY, "127.0.0.1:28010", run_worker=False)
    return service, httpx.ASGITransport(app=app), calls


def signed(path, body=b"{}", key=KEY, timestamp=None):
    stamp = str(int(time.time()) if timestamp is None else timestamp).encode()
    nonce = secrets.token_hex(16).encode()
    return {"content-type": "application/json", "x-stackarr-time": stamp.decode(),
            "x-stackarr-nonce": nonce.decode(),
            "x-stackarr-signature": sign(key, stamp, nonce, b"POST", path.encode(), body)}


@pytest.mark.asyncio
async def test_authenticated_review_approve_status_and_single_use(rpc):
    service, transport, calls = rpc
    client = ControllerClient(ADDRESS, KEY, transport)
    assert await client.request("folders") == {"roots": []}
    assert (await client.request("ports", {"apps": ["seerr"], "ports": {"seerr": 28007}}))["ports"][0]["app"] == "seerr"
    review = await client.request("review", {"apps": ["seerr"], "ports": {"seerr": 28007}})
    assert not calls
    result = await client.request("install", {"review_reference": review["review_reference"]})
    assert len(calls) == 3 and all("--format" in call for call in calls)  # Name allocation is read-only; the worker owns execution.
    assert (await client.request("status"))["operations"][0]["id"] == result["id"]
    with pytest.raises(ControllerConnectionError, match="Review this installation"):
        await client.request("install", {"review_reference": review["review_reference"]})
    await service.deployments.run_one()
    assert (await client.request("status"))["operations"][0]["state"] == "needs-setup"
    assert calls


@pytest.mark.asyncio
async def test_tampering_wrong_key_expiry_replay_and_browser_rejected(rpc):
    service, transport, calls = rpc
    path = "/v1/status"
    async with httpx.AsyncClient(transport=transport, base_url=ADDRESS) as client:
        assert (await client.post(path, content=b"{}", headers={"content-type": "application/json"})).status_code == 401
        headers = signed(path)
        assert (await client.post(path, content=b"{\"changed\":true}", headers=headers)).status_code == 401
        assert (await client.post(path, content=b"{}", headers=signed(path, key=b"x"*32))).status_code == 401
        assert (await client.post(path, content=b"{}", headers=signed(path, timestamp=int(time.time())-120))).status_code == 401
        assert (await client.post(path, content=b"{}", headers=headers)).status_code == 200
        assert (await client.post(path, content=b"{}", headers=headers)).status_code == 409
        for extra in ({"origin": "http://localhost:28000"}, {"host": "attacker.example"}, {"sec-fetch-site": "same-origin"}):
            assert (await client.post(path, content=b"{}", headers={**signed(path), **extra})).status_code == 403
    assert not calls and not service.status()["operations"]


@pytest.mark.asyncio
async def test_invalid_payload_is_redacted_and_size_limited(rpc):
    _, transport, calls = rpc
    async with httpx.AsyncClient(transport=transport, base_url=ADDRESS) as client:
        path = "/v1/review"
        body = json.dumps({"command": "private-password-and-shell-command"}).encode()
        response = await client.post(path, content=body, headers=signed(path, body))
        assert response.status_code == 422
        assert "private-password" not in response.text
        body = b"x" * 17000
        assert (await client.post(path, content=body, headers=signed(path, body))).status_code == 413
        assert (await client.post("/v1/shell", content=b"{}", headers=signed("/v1/shell"))).status_code == 404
        assert (await client.post("/v1/status?other=1", content=b"{}", headers=signed("/v1/status"))).status_code == 403
    assert not calls


@pytest.mark.asyncio
async def test_unsigned_response_redirect_and_connection_loss_are_not_retried():
    calls = []
    def unsigned(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://example.com/collect"})
    client = ControllerClient(ADDRESS, KEY, httpx.MockTransport(unsigned))
    with pytest.raises(ControllerConnectionError, match="identity"):
        await client.request("status")
    assert len(calls) == 1
    def disconnected(request):
        calls.append(request)
        raise httpx.ReadTimeout("sensitive internal address")
    client = ControllerClient(ADDRESS, KEY, httpx.MockTransport(disconnected))
    with pytest.raises(ControllerConnectionError, match="Check progress") as error:
        await client.request("install", {"review_reference": "x"*32})
    assert "sensitive" not in str(error.value)
    assert len(calls) == 2


@pytest.mark.parametrize("address", ["http://example.com:80", "http://localhost:28010/path",
    "http://user:secret@localhost:28010", "http://localhost:28010?x=1", "http://localhost",
    "file:///tmp/controller", "http://localhost:28010#fragment"])
def test_controller_destination_cannot_be_arbitrary(address):
    with pytest.raises(ValueError):
        ControllerClient(address, KEY)


def test_enrollment_key_required():
    with pytest.raises(ValueError):
        ControllerClient(ADDRESS, b"short")


@pytest.mark.asyncio
async def test_discovery_rpc_is_selected_read_only_and_validated(rpc, monkeypatch):
    _, transport, commands = rpc
    calls = []
    async def discover(apps, **options):
        calls.append((apps, options))
        return {'results':[], 'scope':'localhost-and-docker-ports'}
    monkeypatch.setattr('stackarr.discovery.discover', discover)
    client = ControllerClient(ADDRESS, KEY, transport)
    assert (await client.request('discover', {'apps':['sonarr']}))['results'] == []
    assert calls == [(['sonarr'], {'enabled':True, 'include_docker':True})]
    with pytest.raises(ControllerConnectionError):
        await client.request('discover', {'apps':['unknown']})
    assert not commands


@pytest.mark.asyncio
async def test_replay_rejected_after_transport_restart(rpc):
    service, transport, _ = rpc
    headers = signed("/v1/status")
    async with httpx.AsyncClient(transport=transport, base_url=ADDRESS) as client:
        assert (await client.post("/v1/status", content=b"{}", headers=headers)).status_code == 200
    restarted = create_controller_app(service, KEY, "127.0.0.1:28010", run_worker=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url=ADDRESS) as client:
        assert (await client.post("/v1/status", content=b"{}", headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_busy_response_and_internal_error_are_safe(rpc, monkeypatch):
    service, transport, _ = rpc
    client = ControllerClient(ADDRESS, KEY, transport)
    transport.app.busy = True
    with pytest.raises(ControllerConnectionError, match="busy") as busy:
        await client.request("status")
    assert busy.value.status_code == 429
    transport.app.busy = False
    def fail():
        raise RuntimeError("private-internal-key")
    monkeypatch.setattr(service, "status", fail)
    with pytest.raises(ControllerConnectionError, match="could not finish") as error:
        await client.request("status")
    assert "private-internal-key" not in str(error.value)
    assert not transport.app.busy


@pytest.mark.asyncio
async def test_response_from_another_request_is_rejected(rpc):
    _, transport, _ = rpc
    async with httpx.AsyncClient(transport=transport, base_url=ADDRESS) as client:
        recorded = await client.post("/v1/status", content=b"{}", headers=signed("/v1/status"))
    replay = httpx.MockTransport(lambda request: httpx.Response(
        200, content=recorded.content, headers=dict(recorded.headers)))
    with pytest.raises(ControllerConnectionError, match="identity"):
        await ControllerClient(ADDRESS, KEY, replay).request("status")


@pytest.mark.asyncio
async def test_account_setup_private_approval_is_single_use_and_never_exposes_tokens(rpc,monkeypatch):
    from stackarr import finish_setup
    from stackarr.account_setup import Accounts
    service,transport,_=rpc
    plan={'id':'a'*32,'apps':['plex','seerr'],'create':[],'seerr':{'key':'PRIVATE-SEERR'},'plex_key':'PRIVATE-PLEX'}
    async def review(self,identity):
        assert identity==plan['id']
        return plan
    async def apply(self,reviewed):
        assert reviewed==plan
        return {'state':'connected','message':'Ready'}
    async def finish(*args):
        return {'apps':[]}
    monkeypatch.setattr(Accounts,'review',review)
    monkeypatch.setattr(Accounts,'apply',apply)
    monkeypatch.setattr(finish_setup,'finish',finish)
    client=ControllerClient(ADDRESS,KEY,transport)
    public=await client.request('accounts-review',{'id':plan['id']})
    assert 'PRIVATE' not in json.dumps(public)
    result=await client.request('accounts-apply',{'review_reference':public['review_reference']})
    assert result['state']=='connected' and 'PRIVATE' not in json.dumps(result)
    with pytest.raises(ControllerConnectionError):
        await client.request('accounts-apply',{'review_reference':public['review_reference']})
