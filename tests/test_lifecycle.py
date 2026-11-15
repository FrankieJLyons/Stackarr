import asyncio
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_deployment_check import installed as installed

from stackarr.deployment import DeploymentError, Deployments
from stackarr.server import create_app
from stackarr.store import Conflict


@pytest.fixture
def controlled(installed, monkeypatch):
    service, identity, info, calls = installed
    info["Id"] = "b" * 64
    def docker(args, **kwargs):
        calls.append(args)
        if args[2] == "inspect":
            return json.dumps([info])
        assert args[2] in ("start", "stop", "restart")
        assert args[-1] == info["Id"]
        info["State"]["Running"] = args[2] != "stop"
        return info["Id"]
    monkeypatch.setattr(service, "_call", docker)
    return service, identity, info, calls


@pytest.mark.asyncio
async def test_reviewed_stop_start_uses_exact_id_and_never_recreates_or_deletes(controlled):
    service, identity, info, calls = controlled
    for action in ("stop", "start", "restart"):
        review = service.actions.review(identity, "plex", action)
        assert all(args[2] == "inspect" for args in calls)
        service.actions.enqueue(review)
        assert service.actions.busy()
        assert await service.actions.run_one()
        assert service.actions.rows()[0]["state"] == "succeeded"
        assert not service.actions.busy()
        writes = [args for args in calls if args[2] != "inspect"]
        expected = ["--context", "fixture", action, *(["--timeout", "30"] if action in {"stop", "restart"} else []), info["Id"]]
        assert writes == [expected]
        calls.clear()
    assert info["State"]["Running"]
    assert all(row["state"] == "succeeded" for row in service.actions.rows())


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["image", "identity", "media", "state"])
async def test_changed_review_fails_before_any_action(controlled, field):
    service, identity, info, calls = controlled
    review = service.actions.review(identity, "plex", "stop")
    service.actions.enqueue(review)
    if field == "image":
        info["Config"]["Image"] = "changed"
    elif field == "identity":
        info["Id"] = "c" * 64
    elif field == "media":
        info["Mounts"][1]["RW"] = True
    else:
        info["State"]["Running"] = False
    await service.actions.run_one()
    assert service.actions.rows()[0]["state"] == "failed"
    assert all(args[2] == "inspect" for args in calls)
    assert not await service.actions.run_one()


@pytest.mark.asyncio
async def test_lost_response_never_replays_write(controlled, monkeypatch):
    service, identity, info, calls = controlled
    review = service.actions.review(identity, "plex", "stop")
    original = service._call
    def lose_response(args, **kwargs):
        result = original(args, **kwargs)
        if args[2] == "stop":
            raise RuntimeError("private runtime output")
        return result
    monkeypatch.setattr(service, "_call", lose_response)
    service.actions.enqueue(review)
    await service.actions.run_one()
    assert not info["State"]["Running"]
    assert service.actions.rows()[0]["state"] == "failed"
    assert "private runtime" not in json.dumps(service.actions.rows())
    assert not await service.actions.run_one()
    assert sum(args[2] == "stop" for args in calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["queued", "running"])
async def test_restart_requires_new_action_review(controlled, state):
    service, identity, _, _ = controlled
    action_id = service.actions.enqueue(service.actions.review(identity, "plex", "stop"))
    with service.store.db() as db:
        db.execute("UPDATE deployment_actions SET state=? WHERE id=?", (state, action_id))
    restarted = Deployments(service.store)
    assert restarted.actions.rows()[0]["state"] == "interrupted"
    assert not await restarted.actions.run_one()


def test_actions_and_installs_cannot_overlap(controlled):
    service, identity, _, _ = controlled
    review = service.actions.review(identity, "plex", "stop")
    service.actions.enqueue(review)
    with pytest.raises(Conflict, match="progress"):
        service.actions.enqueue(review)
    with pytest.raises(Conflict, match="progress"):
        service.enqueue({})
    with pytest.raises(Conflict, match="progress"):
        service.resume(identity)


def test_external_apps_and_unsupported_actions_are_rejected(controlled):
    service, identity, _, calls = controlled
    for key, action in (("sonarr", "stop"), ("plex", "delete")):
        with pytest.raises(DeploymentError):
            service.actions.review(identity, key, action)
    assert not calls


def test_action_confirmation_is_session_bound_and_single_use(tmp_path):
    async def idle(self):
        await asyncio.sleep(3600)
    with patch.object(Deployments, "work", idle):
        app = create_app(tmp_path, origin="http://localhost:8787", host_checks=True, host_install=True, background=False)
        with TestClient(app, base_url="http://localhost:8787") as client:
            headers = {"Origin": "http://localhost:8787"}
            password = "synthetic test password"
            client.post("/api/setup", json={"password": password, "setup_token": (tmp_path / "setup-token").read_text()}, headers=headers)
            login = client.post("/api/login", json={"password": password}, headers=headers)
            headers["X-CSRF-Token"] = login.json()["csrf"]
            payload = {"deployment": "a" * 32, "app": "plex", "name": "Plex", "action": "stop", "container": "b" * 64, "receipt": "synthetic"}
            endpoint = "/api/deployments/" + "a" * 32 + "/apps/plex/review"
            assert client.post(endpoint, json={"action": "stop"}).status_code == 403
            with patch.object(app.state.deployments.actions, "review", return_value=payload):
                review = client.post(endpoint, json={"action": "stop"}, headers=headers).json()
                # A second login must review independently.
                login = client.post("/api/login", json={"password": password}, headers={"Origin": "http://localhost:8787"})
                headers["X-CSRF-Token"] = login.json()["csrf"]
                assert client.post("/api/deployments/actions/apply", json={"review_token": review["review_token"]}, headers=headers).status_code == 409
                review = client.post(endpoint, json={"action": "stop"}, headers=headers).json()
            try:
                assert client.post("/api/deployments/actions/apply", json={"review_token": review["review_token"]}, headers=headers).status_code == 202
                assert client.post("/api/deployments/actions/apply", json={"review_token": review["review_token"]}, headers=headers).status_code == 409
                assert app.state.deployments.actions.rows()[0]["state"] == "queued"
            finally:
                # This test deliberately disables the worker; no Docker action runs.
                with app.state.store.db() as db:
                    db.execute("UPDATE deployment_actions SET state='interrupted'")
