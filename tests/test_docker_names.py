import json
import ntpath
from types import SimpleNamespace

import pytest
from test_deployment_check import installed  # noqa: F401

from stackarr.deployment_check import check
from stackarr.docker_names import app_project, available_project, controller_project


def test_saved_legacy_receipt_keeps_its_original_resources():
    assert app_project("a" * 32, {}) == "stackarr-owned-" + "a" * 32


@pytest.mark.parametrize("name", ["stackarr-apps", "stackarr-apps-2", "stackarr-apps-10"])
def test_saved_friendly_receipt_keeps_its_name(name):
    assert app_project("a" * 32, {"project": name}) == name


@pytest.mark.parametrize("name", ["foreign", "stackarr-apps-1", "stackarr-apps-02", "stackarr-apps-", "stackarr-apps/x", True, ""])
def test_receipt_cannot_select_an_arbitrary_project(name):
    with pytest.raises(ValueError):
        app_project("a" * 32, {"project": name})


def test_names_skip_stopped_containers_retained_volumes_networks_and_receipts():
    answers = iter(["stackarr-apps\n", "stackarr-apps-2\n", "stackarr-apps-3\n"])
    calls = []

    def call(args):
        calls.append(args)
        return next(answers)

    assert available_project(call, "apps", ["stackarr-apps-4"]) == "stackarr-apps-5"
    assert [args[0] for args in calls] == ["ps", "volume", "network"]
    assert all("--format" in args for args in calls)


def test_first_install_has_no_suffix():
    assert available_project(lambda args: "", "apps") == "stackarr-apps"
    assert available_project(lambda args: "", "controller") == "stackarr-controller"


@pytest.mark.parametrize("actual", [r"D:\Media Fixture\Test Media", "/run/desktop/mnt/host/d/Media Fixture/Test Media", "/host_mnt/d/Media Fixture/Test Media"])
def test_docker_desktop_mount_spellings_match_the_saved_windows_folder(actual, monkeypatch):
    from stackarr import deployment_check

    monkeypatch.setattr(deployment_check, "os", SimpleNamespace(name="nt", path=ntpath))
    assert deployment_check.host_path(actual) == deployment_check.host_path(r"D:\Media Fixture\Test Media")
    assert deployment_check.host_path(actual) != deployment_check.host_path(r"D:\Media Fixture\Other Media")


@pytest.mark.parametrize("name", ["stackarr-controller", "stackarr-controller-2", "stackarr-controller-10", "stackarr-preview-" + "a" * 12, "stackarr-plex-lab-" + "b" * 12])
def test_controller_accepts_readable_and_legacy_names(name):
    assert controller_project(name)


@pytest.mark.parametrize("name", ["other", "stackarr-controller-01", "stackarr-controller-1", True])
def test_controller_rejects_foreign_names(name):
    assert not controller_project(name)


def test_friendly_project_still_checks_ownership_and_allows_scoped_lifecycle(installed):  # noqa: F811
    service, identity, info, calls = installed
    with service.store.db() as db:
        payload = json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])
        payload["project"] = "stackarr-apps"
        db.execute("UPDATE deployments SET payload=? WHERE id=?", (json.dumps(payload), identity))
    info["Id"] = "b" * 64
    info["Config"]["Labels"]["com.docker.compose.project"] = "stackarr-apps"
    info["Mounts"][0]["Name"] = "stackarr-apps_plex-config"
    info["NetworkSettings"]["Networks"] = {"stackarr-apps_control": {}}
    assert check(service, identity)["apps"][0]["state"] == "running"
    assert service.actions.review(identity, "plex", "stop")["container"] == "b" * 64
    assert all(call[-1] == "stackarr-apps-plex-1" for call in calls)
    info["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    assert check(service, identity)["apps"][0]["state"] == "changed"
