import json

import httpx
import pytest
from test_controller_connections import register

from stackarr.controller_connections import finish_owned
from stackarr.store import Store


@pytest.fixture
def seerr_handoff(tmp_path):
    store, identity = Store(tmp_path), "a" * 32
    register(store, identity)
    with store.db() as db:
        db.execute("UPDATE controller_connections SET ports=?", (json.dumps({"seerr": 35055}),))

    class Remote:
        credential = {"api_key": "synthetic-seerr-key"}
        calls = 0

        async def request(self, operation, payload):
            assert operation == "seerr-connection" and payload == {"id": identity}
            self.calls += 1
            return {"id": identity, "port": 35055, "credential": self.credential}

    return store, identity, Remote()


def seerr_api(request):
    assert request.url.host == "host.docker.internal" and request.url.port == 35055
    assert request.headers["X-Api-Key"] == "synthetic-seerr-key"
    return httpx.Response(200, json={"version": "fixture"} if request.url.path.endswith("/status")
                          else dict.fromkeys(("total", "pending", "approved", "declined", "processing", "available"), 0))


async def test_initialized_seerr_handoff_is_encrypted_verified_and_idempotent(seerr_handoff):
    store, identity, remote = seerr_handoff
    result = await finish_owned(store, remote, identity, httpx.MockTransport(seerr_api))
    assert result["apps"][0]["state"] == "connected"
    assert store.secret("seerr") == remote.credential
    assert b"synthetic-seerr-key" not in store.path.read_bytes() and "synthetic-seerr-key" not in json.dumps(result)
    assert store.config()[1].integrations["seerr"].browser_url == "http://localhost:35055"
    assert (await finish_owned(store, remote, identity))["apps"][0]["state"] == "saved" and remote.calls == 1


async def test_unfinished_account_and_later_settings_are_preserved(seerr_handoff):
    store, identity, remote = seerr_handoff
    remote.credential = None
    assert (await finish_owned(store, remote, identity))["apps"][0]["state"] == "needs-setup"
    assert not store.secret("seerr")
    revision, config = store.config()
    store.save(config, revision, {"seerr": {"api_key": "owner-saved-secret"}})
    assert (await finish_owned(store, remote, identity))["apps"][0]["state"] == "changed"
    assert remote.calls == 1 and store.secret("seerr")["api_key"] == "owner-saved-secret"


async def test_rejected_seerr_key_never_saves(seerr_handoff):
    store, identity, remote = seerr_handoff
    result = await finish_owned(store, remote, identity, httpx.MockTransport(lambda request: httpx.Response(401)))
    assert result["apps"][0]["state"] == "waiting" and not store.secret("seerr")
