import copy
import json

import httpx
import pytest

from stackarr.controller_connections import companion_login, finish_owned
from stackarr.store import Store

PORTS = {"tautulli": 42465, "kuma": 42466, "cleanuparr": 42467}
KEYS = {"tautulli": "a" * 32, "kuma": "uk1_" + "b" * 40, "cleanuparr": "c" * 64}


class Remote:
    def __init__(self, identity):
        self.identity = identity
        self.reply = {"id": identity, "apps": {key: {"port": port, "credential": {"api_key": KEYS[key]}} for key, port in PORTS.items()}}

    async def request(self, operation, payload):
        if operation == "companion-login":
            key = payload["app"]
            return {"id": self.identity, "app": key, "port": PORTS[key], "api_key": KEYS[key],
                    "login": {"username": "stackarr", "password": "synthetic-generated-companion-password"}}
        assert operation == "companion-connections"
        return copy.deepcopy(self.reply)


@pytest.fixture
def handoff(tmp_path):
    store, identity = Store(tmp_path), "d" * 32
    with store.db() as db:
        db.execute("CREATE TABLE controller_connections (id TEXT PRIMARY KEY, revision INTEGER, ports TEXT, activated INTEGER DEFAULT 0)")
        db.execute("INSERT INTO controller_connections VALUES(?,?,?,0)", (identity, 1, json.dumps(PORTS)))
    return store, identity, Remote(identity)


def respond(request):
    assert request.method == "GET"
    if request.url.path == "/api/v2":
        return httpx.Response(200, json={"response": {"result": "success", "data": {"sessions": []}}})
    if request.url.path == "/metrics":
        return httpx.Response(200, text='monitor_status{monitor_name="Stackarr Plex"} 1')
    return httpx.Response(200, json={"dryRun": True, "enabled": False, "searchEnabled": False, "proactiveSearchEnabled": False})


async def test_private_companion_handoff_and_login(handoff):
    store, identity, remote = handoff
    result = await finish_owned(store, remote, identity, httpx.MockTransport(respond))
    assert {row["state"] for row in result["apps"]} == {"connected"}
    for key in PORTS:
        assert KEYS[key] not in json.dumps(result)
        assert KEYS[key].encode() not in store.path.read_bytes()
        assert (await companion_login(store, remote, key))["username"] == "stackarr"
    assert {row["state"] for row in (await finish_owned(store, remote, identity))["apps"]} == {"saved"}


@pytest.mark.parametrize("change", [lambda value: value["apps"].pop("kuma"),
    lambda value: value["apps"]["kuma"].update(port=True),
    lambda value: value["apps"]["cleanuparr"].update(credential={"api_key": "bad\nkey"})])
async def test_malformed_companion_handoff_never_saves(handoff, change):
    store, identity, remote = handoff
    change(remote.reply)
    with pytest.raises(ValueError):
        await finish_owned(store, remote, identity, httpx.MockTransport(respond))
    assert store.config()[0] == 1 and not store.secret_names()


async def test_unfinished_companion_does_not_block_others(handoff):
    store, identity, remote = handoff
    remote.reply["apps"]["cleanuparr"]["credential"] = None
    result = await finish_owned(store, remote, identity, httpx.MockTransport(respond))
    assert next(row for row in result["apps"] if row["app"] == "cleanuparr")["state"] == "needs-setup"
    assert set(store.secret_names()) == {'kuma', 'tautulli'}
    assert (await companion_login(Store(store.root), remote, 'kuma'))['username'] == 'stackarr'
