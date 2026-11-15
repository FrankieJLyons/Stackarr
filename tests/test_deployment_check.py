import copy
import json

import pytest

from stackarr.config import Config
from stackarr.deployment import DeploymentError, Deployments
from stackarr.deployment_check import check
from stackarr.installer import compose_plan
from stackarr.store import Store


@pytest.fixture
def installed(tmp_path, monkeypatch):
    service = Deployments(Store(tmp_path / "state"))
    identity = "a" * 32
    project = "stackarr-owned-" + identity
    config = Config()
    config.storage.data_root = str(tmp_path / "media")
    config.integrations["plex"].enabled = True
    config.integrations["plex"].mode = "install"
    compose = compose_plan(config)["compose"]
    context = {"name": "fixture", "endpoint": "unix:///fixture"}
    payload = {"apps": ["plex"], "compose": compose, "context": context}
    with service.store.db() as db:
        db.execute("INSERT INTO deployments VALUES(?,?,?,?,?,?)", (identity, "needs-setup", "Ready", 0, 0, json.dumps(payload)))
    directory = service.store.root / "deployments" / identity
    directory.mkdir(parents=True)
    (directory / "compose.json").write_text(json.dumps(compose, sort_keys=True), encoding="utf-8")
    info = {
        "Config": {"Image": compose["services"]["plex"]["image"], "Labels": {"com.docker.compose.project": project, "com.docker.compose.service": "plex"}},
        "Mounts": [{"Destination": "/config", "Type": "volume", "Name": project + "_plex-config"},
                   {"Destination": "/data", "Type": "bind", "Source": config.storage.data_root, "RW": False}],
        "HostConfig": {"PortBindings": {"32400/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32400"}]}, "SecurityOpt": ["no-new-privileges:true"]},
        "NetworkSettings": {"Networks": {project + "_control": {}}},
        "State": {"Running": True},
    }
    calls = []
    monkeypatch.setattr(service, "context", lambda: context)
    monkeypatch.setattr(service, "_call", lambda args, **kwargs: calls.append(args) or json.dumps([info]))
    return service, identity, info, calls


def test_matching_and_stopped_containers_are_checked_without_writes(installed):
    service, identity, info, calls = installed
    assert check(service, identity)["apps"][0]["state"] == "running"
    info["State"]["Running"] = False
    info["NetworkSettings"]["Ports"] = {}  # Docker removes live bindings while stopped.
    assert check(service, identity)["apps"][0]["state"] == "stopped"
    assert all(args == ["--context", "fixture", "inspect", "stackarr-owned-" + identity + "-plex-1"] for args in calls)


@pytest.mark.parametrize("change,detail", [
    (lambda info: info["Config"]["Labels"].update({"com.docker.compose.project": "foreign"}), "ownership"),
    (lambda info: info["Config"].update(Image="different-image"), "image"),
    (lambda info: info["Mounts"][0].update(Name="foreign-volume"), "configuration volume"),
    (lambda info: info["Mounts"][1].update(RW=True), "media mounts or access"),
    (lambda info: info["Mounts"][1].update(Source="different-folder"), "media mounts or access"),
    (lambda info: info["HostConfig"]["PortBindings"]["32400/tcp"][0].update(HostIp="0.0.0.0"), "published ports"),
    (lambda info: info["NetworkSettings"]["Networks"].update(foreign={}), "private network"),
    (lambda info: info["HostConfig"].update(Privileged=True), "privileges"),
])
def test_drift_is_reported_without_exposing_values_or_repairing(installed, change, detail):
    service, identity, info, calls = installed
    change(info)
    before = copy.deepcopy(info)
    result = check(service, identity)
    assert result["apps"][0]["state"] == "changed"
    assert detail in result["apps"][0]["detail"]
    assert "foreign" not in json.dumps(result) and "different-folder" not in json.dumps(result)
    assert info == before and len(calls) == 1


def test_modified_plan_stops_before_contacting_docker(installed):
    service, identity, _, calls = installed
    (service.store.root / "deployments" / identity / "compose.json").write_text("{}")
    with pytest.raises(DeploymentError, match="changed"):
        check(service, identity)
    assert not calls


def test_missing_container_error_is_redacted(installed, monkeypatch):
    service, identity, _, _ = installed
    def fail(*args, **kwargs):
        raise DeploymentError("private engine output")
    monkeypatch.setattr(service, "_call", fail)
    result = check(service, identity)
    assert result["apps"][0]["state"] == "unavailable"
    assert "private engine output" not in json.dumps(result)


def test_container_dashboard_cannot_inspect_host(client, auth):
    endpoint = "/api/deployments/" + "a" * 32 + "/check"
    assert client.post(endpoint).status_code == 403
    assert client.post(endpoint, headers=auth).status_code == 409
