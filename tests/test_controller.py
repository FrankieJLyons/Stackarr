import json

import pytest
from pydantic import ValidationError
from test_deployment import image_answer

from stackarr.controller import InstallationController, InstallIntent
from stackarr.store import Conflict, Store


@pytest.fixture
def controller(tmp_path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    (media / "preserve.txt").write_text("unchanged")
    now = [100.0]
    service = InstallationController(Store(tmp_path / "controller"),
        [{"path": str(media), "host_path": str(media), "label": "Test media"}],
        28000, clock=lambda: now[0])
    monkeypatch.setattr(service.deployments, "context", lambda: {"name": "fixture", "endpoint": "unix:///fixture"})
    monkeypatch.setattr("stackarr.deployment.preflight", lambda config: [{"check": "fixture", "ok": True}])
    calls = []
    monkeypatch.setattr(service.deployments, "network_capacity", lambda *args: {"state": "available"})
    monkeypatch.setattr(service.deployments, "_call", lambda args, **kwargs: calls.append(args) or image_answer(args))
    monkeypatch.setattr("stackarr.seerr_storage.prepare", lambda *args: None)
    return service, calls, now, media


def intent(**changes):
    return {"apps": ["seerr"], "ports": {"seerr": 28007}, **changes}


@pytest.mark.parametrize("changes", [
    {"command": "docker prune"}, {"compose": {}}, {"image": "untrusted:latest"},
    {"host_path": "C:/"}, {"privileged": True}, {"apps": ["unknown"]},
    {"apps": ["seerr", "seerr"]}, {"ports": {"seerr": True}},
    {"ports": {"seerr": "28007"}}, {"ports": {"seerr": 65536}},
    {"ports": {"plex": 28007}}, {"folder": -1}, {"relative": "../"},
    {"apps": ["seerr", "kuma"], "ports": {"seerr": 28007, "kuma": 28007}},
])
def test_rejects_untrusted_install_parameters(changes):
    with pytest.raises(ValidationError):
        InstallIntent.model_validate(intent(**changes))


def test_review_does_not_install_or_change_active_apps(controller):
    service, calls, _, media = controller
    before = service.store.config()
    reviewed = service.review(intent())
    assert not calls
    assert service.store.config() == before
    assert not service.status()["operations"]
    assert reviewed["plan"]["apps"][0]["port"] == "28007"
    assert "@sha256:" in reviewed["plan"]["apps"][0]["image"]
    assert (media / "preserve.txt").read_text() == "unchanged"


def test_review_binds_request_quality_and_displays_it_before_approval(controller):
    service, calls, _, _ = controller
    reviewed = service.review({"apps": ["sonarr", "radarr"], "ports": {"sonarr": 28989, "radarr": 27878},
        "folder": 0, "quality_profiles": {"sonarr": "HD-1080p", "radarr": "Ultra-HD"}})
    rows = {row["app"]: row for row in reviewed["plan"]["quality_setup"]}
    assert rows["sonarr"]["quality"] == "1080p" and rows["radarr"]["quality"] == "4K / UHD"
    assert service.pending[2]["config"]["integrations"]["radarr"]["quality_profile"] == "Ultra-HD"
    assert not calls


@pytest.mark.asyncio
async def test_single_use_approval_runs_only_reviewed_app(controller):
    service, calls, _, _ = controller
    review = service.review(intent())
    identity = service.install(review["review_reference"])["id"]
    assert service.status()["operations"][0]["id"] == identity
    with pytest.raises(Conflict):
        service.install(review["review_reference"])
    assert len(calls) == 3 and all("--format" in call for call in calls)
    await service.deployments.run_one()
    assert service.status()["operations"][0]["state"] == "needs-setup"
    assert service.status()["operations"][0]["links"] == [{"app": "seerr", "url": "http://localhost:28007"}]
    assert all("stackarr-apps" in call for call in calls if "compose" in call)
    assert not any("prune" in call or "--volumes" in call for call in calls)
    assert not service.store.config()[1].integrations["plex"].enabled
    assert "secrets" not in json.dumps(service.status())


@pytest.mark.asyncio
async def test_second_installation_batch_preserves_first_app(controller):
    service, calls, _, _ = controller
    first = service.install(service.review(intent())["review_reference"])["id"]
    await service.deployments.run_one()
    before = service.store.config()[1].integrations["seerr"]
    with service.store.db() as db:
        original = db.execute("SELECT payload FROM deployments WHERE id=?", (first,)).fetchone()[0]
    first_calls = len(calls)
    second = service.install(service.review({"apps": ["tautulli"],
        "ports": {"tautulli": 28008}})["review_reference"])["id"]
    await service.deployments.run_one()
    rows = {row["id"]: row for row in service.status()["operations"]}
    assert rows[first]["state"] == rows[second]["state"] == "needs-setup"
    assert service.store.config()[1].integrations["seerr"] == before
    with service.store.db() as db:
        assert db.execute("SELECT payload FROM deployments WHERE id=?", (first,)).fetchone()[0] == original
    assert all("stackarr-apps-2" in call for call in calls[first_calls:] if "compose" in call)
    assert not any("--volumes" in call or "prune" in call for call in calls)


def test_host_port_checks_are_scoped_and_do_not_install(controller):
    service, calls, _, _ = controller
    checked = service.ports(intent())
    assert checked["ports"][0]["port"] == 28007
    assert checked["ports"][0]["status"] in {"available", "unavailable"}
    assert service.ports(intent(), suggest=True)["suggestions"][0]["app"] == "seerr"
    assert not calls and not service.status()["operations"]
    assert service.ports(intent(ports={"seerr": 28000}))["ports"][0]["status"] == "reserved"
    assert service.ports(intent(ports={"seerr": 28010}), suggest=True)["suggestions"][0]["port"] not in {28000, 28010}


def test_host_folder_browser_only_returns_approved_paths(controller):
    service, calls, _, media = controller
    child = media / "Movies"
    child.mkdir()
    assert service.folders()["roots"] == [{"id": 0, "name": "Test media"}]
    assert service.folders(0)["folders"][0]["name"] == "Movies"
    assert service.folders(0, "Movies")["host_path"] == str(child)
    for root, relative in ((1, ""), (0, "../outside"), (None, "Movies")):
        with pytest.raises(ValueError):
            service.folders(root, relative)
    assert service.status()["folder_browser"] is True
    assert not calls


def test_expiry_replacement_and_wrong_reference(controller):
    service, calls, now, _ = controller
    first = service.review(intent())
    second = service.review(intent())
    for reference in (first["review_reference"], "wrong", "非ASCII", None):
        with pytest.raises(Conflict):
            service.install(reference)
    now[0] += 301
    with pytest.raises(Conflict, match="expired"):
        service.install(second["review_reference"])
    assert not calls


@pytest.mark.parametrize("relative", ["../", "/etc", "C:/Windows", "..\\outside"])
def test_folder_reference_cannot_escape(controller, relative):
    service, calls, _, _ = controller
    with pytest.raises(ValueError):
        service.review(intent(folder=0, relative=relative))
    assert not calls


def test_missing_media_root_reserved_port_and_changed_revision(controller):
    service, calls, _, _ = controller
    with pytest.raises(ValueError, match="approved media folder"):
        service.review(intent(apps=["plex"], ports={"plex": 28001}))
    with pytest.raises(ValueError, match="dashboard or private setup port"):
        service.review(intent(ports={"seerr": 28000}))
    review = service.review(intent())
    revision, config = service.store.config()
    service.store.save(config, revision, {})
    with pytest.raises(Conflict, match="changed"):
        service.install(review["review_reference"])
    assert not calls


def test_pending_install_blocks_new_review(controller):
    service, calls, _, _ = controller
    service.install(service.review(intent())["review_reference"])
    calls.clear()
    with pytest.raises(Conflict, match="needs attention"):
        service.review(intent(apps=["kuma"], ports={"kuma": 28009}))
    assert not calls
