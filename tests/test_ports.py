import socket

import pytest
from test_controller import controller as controller_fixture

from stackarr.onboarding import AppChoice, SetupDraft
from stackarr.ports import PortsUnavailable, available, check, suggestions
from stackarr.store import Conflict

controller = controller_fixture


def test_nonexclusive_wildcard_listener_is_never_shadowed():
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen()
        assert not available(listener.getsockname()[1])
        listener.settimeout(.01)
        with pytest.raises(TimeoutError):
            listener.accept()


def test_occupied_port_is_avoided_without_contacting_existing_listener():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        draft = SetupDraft(apps=["seerr"], choices={"seerr": AppChoice(port=port)})
        rows = suggestions(draft)
        assert rows[0]["previous"] == port and rows[0]["port"] != port
        occupied.settimeout(.01)
        try:
            connection, _ = occupied.accept()
        except TimeoutError:
            pass
        else:
            connection.close()
            raise AssertionError("Port suggestion contacted an existing service")


def test_connected_apps_are_excluded_and_suggestions_are_unique():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    draft = SetupDraft(apps=["plex", "sonarr", "radarr"], choices={
        "plex": AppChoice(mode="connect", url="http://existing.example"),
        "sonarr": AppChoice(port=port), "radarr": AppChoice(port=port)})
    rows = suggestions(draft)
    assert [r["app"] for r in rows] == ["sonarr", "radarr"]
    assert len({r["port"] for r in rows}) == 2


def test_container_dashboard_does_not_inspect_host_ports(client, auth):
    assert client.post("/api/onboarding/suggest-ports").status_code == 403
    assert client.post("/api/onboarding/suggest-ports", headers=auth).status_code == 409
    assert client.post("/api/onboarding/check-ports").status_code == 403
    assert client.post("/api/onboarding/check-ports", headers=auth).status_code == 409


def test_check_reports_conflicts_and_excludes_existing_apps():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        draft = SetupDraft(apps=["plex", "sonarr", "radarr"], choices={
            "plex": AppChoice(mode="connect"), "sonarr": AppChoice(port=port), "radarr": AppChoice(port=port)})
        rows = check(draft)
        assert [r["status"] for r in rows] == ["unavailable", "duplicate"]
        assert [r["app"] for r in rows] == ["sonarr", "radarr"]


def test_reserved_and_duplicate_ports_can_be_repaired_without_installing(controller):
    service, calls, _, _ = controller
    intent = {"apps": ["sonarr", "radarr"], "ports": {"sonarr": 28000, "radarr": 28000}}
    assert {row["status"] for row in service.ports(intent)["ports"]} == {"reserved"}
    choices = service.ports(intent, suggest=True)["suggestions"]
    assert len({row["port"] for row in choices}) == 2
    assert not {row["port"] for row in choices} & service.reserved_ports
    assert not calls and not service.deployments.rows()


def test_port_taken_after_review_requires_fresh_approval(controller):
    service, calls, _, _ = controller
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    review = service.review({"apps": ["seerr"], "ports": {"seerr": port}})
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen()
        with pytest.raises(PortsUnavailable):
            service.install(review["review_reference"])
        assert not service.deployments.rows() and not calls
        with pytest.raises(Conflict):
            service.install(review["review_reference"])


async def test_port_taken_during_pull_stops_before_folders_or_containers(controller, monkeypatch):
    service, calls, _, _ = controller
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    identity = service.install(service.review({"apps": ["seerr"], "ports": {"seerr": port}})["review_reference"])["id"]
    with socket.socket() as listener:
        def pull(*args):
            listener.bind(("127.0.0.1", port))
            listener.listen()
        monkeypatch.setattr(service.deployments, "_pull", pull)
        monkeypatch.setattr("stackarr.managed_storage.prepare", lambda *args: pytest.fail("Media folders must stay untouched"))
        await service.deployments.run_one()
        assert service.deployments.rows()[0]["state"] == "ports-blocked"
        assert not any("up" in call for call in calls)
        assert not service.store.config()[1].integrations["seerr"].enabled
        changed = service.ports({"apps": ["seerr"], "ports": {"seerr": port}}, suggest=True)["suggestions"][0]["port"]
        reviewed = service.review({"apps": ["seerr"], "ports": {"seerr": changed}})
        second = service.install(reviewed["review_reference"])["id"]
        assert second != identity
