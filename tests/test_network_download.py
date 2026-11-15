import asyncio
import ipaddress
import json
import subprocess

import pytest
from test_deployment import deployment  # noqa: F401

from stackarr.deployment import DeploymentError, Deployments
from stackarr.docker_failures import classify
from stackarr.docker_networks import estimate, inspect


def inventory(occupied, configured=None, existing=None):
    calls = []
    def command(args):
        calls.append(args)
        if args[0] == "info":
            return json.dumps(configured)
        if "ls" in args:
            return "a" * 64
        return json.dumps({"name": existing or "fixture", "labels": {
            "com.docker.compose.project": (existing or "fixture").removesuffix("_control"),
            "com.docker.compose.network": "control"}, "subnets": [{"Subnet": value} for value in occupied]})
    return calls, command


def test_capacity_estimates_overlaps_without_allocating_or_disclosing_inventory():
    calls, command = inventory(["198.18.0.0/26", "198.18.0.0/27"], [{"Base": "198.18.0.0/24", "Size": 26}])
    result = inspect(command)
    assert result["estimated_free"] == 3
    assert not any(set(row) & {"create", "rm", "prune", "up"} for row in calls)
    assert "198.18" not in json.dumps(result) and "fixture" not in json.dumps(result)
    pools = [(ipaddress.ip_network("198.18.0.0/24"), 32)]
    assert estimate(pools, [ipaddress.ip_network("198.18.0.0/25")]) == 128


def test_exhaustion_and_existing_owned_network_are_distinct():
    _, command = inventory(["198.18.0.0/24"], [{"Base": "198.18.0.0/24", "Size": 25}], "stackarr-owned-test_control")
    result = inspect(command, "stackarr-owned-test_control")
    assert result["state"] == "exhausted" and result["existing_network"]
    assert "does not remove" in result["detail"]
    result = inspect(command, "another_control")
    assert not result["existing_network"]


@pytest.mark.parametrize("bad", ["private engine output", "[]", "{}", '"private path"'])
def test_unknown_inventory_is_redacted(bad):
    assert inspect(lambda args: bad)["state"] == "unknown"
    assert "private" not in json.dumps(inspect(lambda args: bad))


def test_documented_default_pools_and_ipv6_overlap():
    _, command = inventory(["172.17.0.0/16", "2001:db8::/32"])
    result = inspect(command)
    assert result["pool_source"] == "built-in" and result["estimated_free"] == 30


@pytest.mark.parametrize("error", ["unexpected EOF", "connection reset by peer", "TLS handshake timeout", "context canceled", "429 too many requests"])
def test_download_only_transient_retries_and_error_redaction(error):
    kind, message, retry = classify(error + " private-token", downloading=True)
    assert kind == "download-interrupted" and retry and "private-token" not in message
    assert not classify(error)[2]


def test_known_permanent_and_capacity_failures_do_not_retry():
    for error, expected in [("manifest unknown", "download-unavailable"), ("no space left on device", "download-storage"),
                            ("all predefined address pools have been fully subnetted", "network-capacity")]:
        kind, _, retry = classify(error, downloading=True)
        assert kind == expected and not retry


def test_actual_timeout_classification_is_limited_to_downloads(tmp_path, monkeypatch):
    from stackarr.store import Store
    monkeypatch.setattr("stackarr.deployment.executable", lambda: "fixture")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private command", 1)
    service = Deployments(Store(tmp_path), runner=timeout)
    with pytest.raises(DeploymentError) as caught:
        service._call(["compose", "pull"])
    assert caught.value.retryable and caught.value.kind == "download-interrupted"
    with pytest.raises(DeploymentError) as caught:
        service._call(["compose", "up"])
    assert not caught.value.retryable


def test_exhausted_network_prevents_review_and_preserves_data(deployment, monkeypatch):  # noqa: F811
    service, calls = deployment
    before = service.store.config()
    monkeypatch.setattr(service, "network_capacity", lambda *args: {"state": "exhausted"})
    with pytest.raises(DeploymentError, match="no unallocated"):
        service.review()
    assert service.store.config() == before and not service.rows() and not calls
    monkeypatch.setattr(service, "network_capacity", lambda *args: {"state": "exhausted", "existing_network": True})
    assert service.require_network({"name": "fixture"}, "existing")["existing_network"]


@pytest.mark.asyncio
async def test_incomplete_image_cannot_create_app_data_and_retries_same_saved_plan(deployment, monkeypatch):  # noqa: F811
    service, calls = deployment
    reviewed = service.review()
    identity = service.enqueue(reviewed)
    original = service._call
    def missing(args, **kwargs):
        if "image" in args:
            return json.dumps({"id": "sha256:" + "a" * 64, "digests": [], "os": "linux", "arch": "amd64"})
        return original(args, **kwargs)
    monkeypatch.setattr(service, "_call", missing)
    monkeypatch.setattr("stackarr.managed_storage.prepare", lambda *args: pytest.fail("No folders before complete image verification"))
    await service.run_one()
    row = service.rows()[0]
    assert row["state"] == "failed" and row["phase"] == "downloading" and row["diagnostic"] == "download-verification"
    assert not any("up" in args for args in calls)
    service.resume(identity)
    with service.store.db() as db:
        saved = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
    assert saved["compose"] == reviewed["compose"] and service.rows()[0]["id"] == identity


def test_restart_reports_download_without_replaying_or_losing_the_receipt(deployment):  # noqa: F811
    service, calls = deployment
    identity = service.enqueue(service.review())
    calls.clear()
    service._step(identity, "downloading")
    with service.store.db() as db:
        db.execute("UPDATE deployments SET state='running' WHERE id=?", (identity,))
    restarted = Deployments(service.store)
    row = restarted.rows()[0]
    assert row["state"] == "interrupted" and row["phase"] == "downloading"
    assert "download interrupted" in row["message"] and not calls


def test_starting_candidate_controller_preserves_older_idle_database(deployment):  # noqa: F811
    from stackarr.self_update import fingerprint

    service, _ = deployment
    before = fingerprint(service.store.root)
    restarted = Deployments(service.store)
    assert restarted.rows() == [] and fingerprint(service.store.root) == before
    with service.store.db() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='deployment_steps'").fetchone()


@pytest.mark.asyncio
async def test_download_cancellation_never_starts_apps(deployment, monkeypatch):  # noqa: F811
    service, calls = deployment
    service.enqueue(service.review())
    calls.clear()
    def cancel(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(service, "execute", cancel)
    with pytest.raises(asyncio.CancelledError):
        await service.run_one()
    assert not calls
