import asyncio
import copy
import json

import pytest
from test_app_maintenance import maintenance  # noqa: F401

from stackarr.config import Config
from stackarr.controller import InstallationController
from stackarr.controller_connections import refresh_ports
from stackarr.deployment import DeploymentError
from stackarr.docker_failures import classify
from stackarr.install_ports import LABEL, InstallPorts
from stackarr.installer import compose_plan
from stackarr.ports import PortsUnavailable
from stackarr.store import Conflict, Store


@pytest.fixture
def partial(maintenance, monkeypatch):  # noqa: F811
    service, identity, flags, calls = maintenance
    with service.store.db() as db:
        payload = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    project = "stackarr-owned-" + identity
    flags["container"]["State"].update(Running=False, Status="created")
    flags["container"]["NetworkSettings"]["Networks"] = {}
    flags["container"]["HostConfig"]["NetworkMode"] = project + "_control"
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='failed' WHERE id=?", (identity,))
    service._step(identity, "starting", "startup-port-conflict")
    original = service._call
    def docker(args, **kwargs):
        if args[2:4] == ["network", "ls"]:
            return "f" * 64
        if args[2:4] == ["volume", "ls"]:
            return project + "_plex-config" if flags["volume"] else ""
        return original(args, **kwargs)
    monkeypatch.setattr(service, "_call", docker)
    busy = {32400}
    monkeypatch.setattr("stackarr.install_ports.available", lambda port: port not in busy)
    monkeypatch.setattr("stackarr.ports.available", lambda port: port not in busy)
    return service, identity, payload, flags, calls, busy


@pytest.mark.parametrize("message", ["port is already allocated", "bind: address already in use", "Ports are not available", "Only one usage of each socket address is normally permitted"])
def test_late_port_errors_are_actionable_redacted_and_not_retried(message):
    kind, public, retry = classify(message + " private-output")
    assert kind == "startup-port-conflict" and "private-output" not in public and not retry
    assert classify(message, downloading=True)[0] != kind


def test_read_only_review_retains_partial_state_and_changes_only_approved_ports(partial):
    service, identity, payload, flags, calls, _ = partial
    before = copy.deepcopy(flags)
    review = InstallPorts(service).review(identity, {42400})
    assert flags == before and service.rows()[0]["state"] == "failed"
    assert review["ports"]["plex"] != 32400 and review["ports"]["plex"] != 42400
    assert review["target"]["compose"]["volumes"] == payload["compose"]["volumes"]
    assert review["target"]["compose"]["services"]["plex"]["volumes"] == payload["compose"]["services"]["plex"]["volumes"]
    assert not any(set(args) & {"up", "stop", "rm", "create", "prune"} for args in calls)


def test_approval_publishes_one_durable_transition_before_recipe_changes(partial):
    service, identity, payload, _, _, _ = partial
    helper = InstallPorts(service)
    review = helper.review(identity)
    filename = service.store.root / "deployments" / identity / "compose.json"
    old = filename.read_bytes()
    result = helper.approve(review)
    assert result["id"] == identity and filename.read_bytes() == old and service.rows()[0]["state"] == "queued"
    with service.store.db() as db:
        saved = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
        assert db.execute("SELECT count(*) FROM deployments").fetchone()[0] == 1
    assert saved["install_ports"]["source"]["compose"] == payload["compose"]
    helper.reconcile(identity, saved, filename)
    assert json.loads(filename.read_text()) == saved["compose"]
    helper.reconcile(identity, saved, filename)
    with pytest.raises(Conflict):
        helper.approve(review)


def test_proposed_port_taken_before_approval_preserves_receipt_and_recipe(partial):
    service, identity, payload, _, _, busy = partial
    helper = InstallPorts(service)
    review = helper.review(identity)
    busy.add(review["ports"]["plex"])
    with pytest.raises(Conflict, match="became busy"):
        helper.approve(review)
    assert service.rows()[0]["state"] == "failed"
    assert helper.read(identity) == payload
    assert helper.review(identity)["ports"]["plex"] not in busy


def test_freed_original_port_offers_original_address_resume(partial):
    service, identity, _, _, _, busy = partial
    busy.clear()
    with pytest.raises(Conflict, match="Resume installation"):
        InstallPorts(service).review(identity)


def test_original_address_resume_recreates_only_unstarted_app_with_retained_storage(partial):
    service, identity, payload, _, _, busy = partial
    busy.clear()
    service.resume(identity)
    with service.store.db() as db:
        target = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    assert target["install_ports"]["ports"] == {"plex": 32400}
    assert target["compose"]["services"]["plex"]["labels"][LABEL] == target["install_ports"]["generation"]
    assert target["compose"]["services"]["plex"]["volumes"] == payload["compose"]["services"]["plex"]["volumes"]


def test_original_address_resume_refuses_a_still_occupied_port(partial):
    service, identity, _, _, _, _ = partial
    with pytest.raises(Conflict, match="Review available ports"):
        InstallPorts(service).resume_original(identity)
    assert service.rows()[0]["state"] == "failed"


def test_running_app_stopped_after_approval_is_preserved_without_restart(partial):
    service, identity, _, flags, calls, _ = partial
    flags["container"]["State"].update(Running=True, Status="running")
    flags["container"]["NetworkSettings"]["Networks"] = {"stackarr-owned-" + identity + "_control": {}}
    helper = InstallPorts(service)
    helper.resume_original(identity)
    with service.store.db() as db:
        target = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    flags["container"]["State"].update(Running=False, Status="exited")
    with pytest.raises(DeploymentError, match="changed state"):
        helper.reconcile(identity, target, service.store.root / "deployments" / identity / "compose.json")
    assert not any(set(args) & {"up", "stop", "rm", "create"} for args in calls)


def test_busy_port_before_recreation_cannot_abandon_retained_recovery_volumes(partial, monkeypatch):
    service, identity, _, _, _, _ = partial
    InstallPorts(service).approve(InstallPorts(service).review(identity))
    with service.store.db() as db:
        before = db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0]
    def occupied(*args):
        raise PortsUnavailable("Earlier fresh-install guidance")
    monkeypatch.setattr(service, "execute", occupied)
    asyncio.run(service.run_one())
    row = service.rows()[0]
    assert row["state"] == "failed" and row["diagnostic"] == "startup-port-conflict"
    assert "same installation" in row["message"] and "Earlier fresh-install" not in row["message"]
    with service.store.db() as db:
        assert db.execute("SELECT count(*) FROM deployments").fetchone()[0] == 1
        assert db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0] == before


def test_running_container_and_shared_storage_are_never_retargeted(partial):
    service, identity, _, flags, _, _ = partial
    flags["container"]["State"].update(Running=True, Status="running")
    flags["container"]["NetworkSettings"]["Networks"] = {"stackarr-owned-" + identity + "_control": {}}
    with pytest.raises(Conflict, match="available now"):
        InstallPorts(service).review(identity)
    flags["shared"] = True
    with pytest.raises(DeploymentError, match="shared"):
        InstallPorts(service).review(identity)


@pytest.mark.parametrize("change", ["privileged", "environment", "network", "file"])
def test_changed_partial_resources_fail_before_any_mutation(partial, change):
    service, identity, _, flags, calls, _ = partial
    if change == "privileged":
        flags["container"]["HostConfig"]["Privileged"] = True
    elif change == "environment":
        flags["container"]["Config"]["Env"].append("PRIVATE_CHANGED=value")
    elif change == "network":
        flags["container"]["HostConfig"]["NetworkMode"] = "host"
    else:
        (service.store.root / "deployments" / identity / "compose.json").write_text('{}')
    with pytest.raises(DeploymentError):
        InstallPorts(service).review(identity)
    assert not any(set(args) & {"up", "stop", "rm", "create"} for args in calls)


def test_reconcile_accepts_only_a_known_generation_target_after_interruption(partial):
    service, identity, _, flags, calls, _ = partial
    helper = InstallPorts(service)
    review = helper.review(identity)
    helper.approve(review)
    with service.store.db() as db:
        target = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    filename = service.store.root / "deployments" / identity / "compose.json"
    helper.reconcile(identity, target, filename)
    info = flags["container"]
    info["Id"] = "1" * 64
    info["HostConfig"]["PortBindings"]["32400/tcp"][0]["HostPort"] = str(review["ports"]["plex"])
    info["Config"]["Labels"][LABEL] = review["generation"]
    info["State"].update(Running=True, Status="running")
    info["NetworkSettings"]["Networks"] = {"stackarr-owned-" + identity + "_control": {}}
    info["NetworkSettings"]["Ports"] = {"32400/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(review["ports"]["plex"])}]}
    helper.reconcile(identity, target, filename)
    helper.start(identity, target, ["--context", "fixture", "compose"])
    assert not any("up" in args for args in calls)
    info["NetworkSettings"]["Ports"] = {}
    with pytest.raises(DeploymentError, match="published address"):
        helper.start(identity, target, ["--context", "fixture", "compose"])
    info["Config"]["Labels"][LABEL] = "2" * 32
    with pytest.raises(DeploymentError):
        helper.reconcile(identity, target, filename)


def test_qbittorrent_host_target_and_webui_port_move_together(tmp_path):
    config = Config()
    config.storage.data_root = str(tmp_path)
    config.integrations["qbittorrent"].enabled = True
    config.integrations["qbittorrent"].mode = "install"
    config.integrations["qbittorrent"].port = 8080
    compose = compose_plan(config)["compose"]
    compose["networks"] = {"control": {}}
    compose["services"]["qbittorrent"].update(image="lscr.io/linuxserver/qbittorrent@sha256:" + "d" * 64, platform="linux/amd64",
        logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}})
    source = {"config": config.model_dump(), "compose": compose, "apps": ["qbittorrent"]}
    target = InstallPorts.target(source, {"qbittorrent": 18080}, "a" * 32, {"qbittorrent": {"container": "b" * 64}})
    port = target["compose"]["services"]["qbittorrent"]["ports"][0]
    assert port["target"] == 18080 and port["published"] == "18080" and port["host_ip"] == "127.0.0.1"
    assert target["compose"]["services"]["qbittorrent"]["environment"]["WEBUI_PORT"] == "18080"
    assert target["compose"]["services"]["qbittorrent"]["volumes"] == source["compose"]["services"]["qbittorrent"]["volumes"]


def test_controller_port_review_is_single_use_and_expires(partial):
    service, identity, _, _, _, _ = partial
    now = [100.0]
    controller = InstallationController(service.store, [], 28000, deployments=service, clock=lambda: now[0])
    reviewed = controller.managed_review(identity, "install-ports")
    now[0] += 301
    with pytest.raises(Conflict, match="Review"):
        controller.managed_apply(reviewed["review_reference"])
    reviewed = controller.managed_review(identity, "install-ports")
    assert controller.managed_apply(reviewed["review_reference"])["id"] == identity
    with pytest.raises(Conflict):
        controller.managed_apply(reviewed["review_reference"])


def test_lost_response_refreshes_only_previously_reviewed_unactivated_bindings(tmp_path):
    store = Store(tmp_path)
    with store.db() as db:
        db.execute("CREATE TABLE controller_connections(id TEXT PRIMARY KEY,revision INTEGER,ports TEXT,activated INTEGER)")
        for identity, active in [("a" * 32, 0), ("b" * 32, 1)]:
            db.execute("INSERT INTO controller_connections VALUES(?,?,?,?)", (identity, 1, json.dumps({"plex": 32400}), active))
    operations = [{"id": identity, "apps": ["plex"], "ports": {"plex": 42400}, "port_recovery": True} for identity in ("a" * 32, "b" * 32, "c" * 32)]
    refresh_ports(store, operations)
    with store.db() as db:
        assert json.loads(db.execute("SELECT ports FROM controller_connections WHERE id=?", ("a" * 32,)).fetchone()[0]) == {"plex": 42400}
        assert json.loads(db.execute("SELECT ports FROM controller_connections WHERE id=?", ("b" * 32,)).fetchone()[0]) == {"plex": 32400}
        assert db.execute("SELECT count(*) FROM controller_connections").fetchone()[0] == 2
