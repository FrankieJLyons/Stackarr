import copy
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from stackarr.config import Dashboard
from stackarr.overview import owned_storage


def test_appearance_is_public_but_configuration_and_storage_require_login(client):
    client.post("/api/logout", headers={"Origin": "http://testserver"})
    assert client.get("/api/appearance").json() == {"appearance": "dark", "accent": "blue"}
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/overview/storage").status_code == 401
    icon = client.get("/api/appearance/icon.svg")
    assert icon.status_code == 200 and "#78b7ff" in icon.text


def test_saved_appearance_contains_only_validated_presets_and_widget_ids():
    assert Dashboard().accent == "blue"
    for accent in ["blue", "red", "yellow", "green", "orange", "purple"]:
        for mode in ["dark", "light", "system"]:
            assert Dashboard(accent=accent, appearance=mode).accent == accent
    for widgets in [["unknown"], ["downloads", "downloads"]]:
        with pytest.raises(ValidationError):
            Dashboard(overview_widgets=widgets)
    with pytest.raises(ValidationError):
        Dashboard(accent="url(attacker)")


def test_appearance_save_preserves_connections_credentials_and_unedited_preferences(client, auth):
    data = client.get("/api/config").json()
    before = copy.deepcopy(data["config"])
    data["config"]["dashboard"].update(accent="purple", appearance="light", overview_widgets=["downloads", "storage"])
    response = client.put("/api/config", headers=auth, json={"revision": data["revision"], "config": data["config"], "credentials": {}})
    assert response.status_code == 200
    after = client.get("/api/config").json()["config"]
    assert after["integrations"] == before["integrations"]
    assert after["storage"] == before["storage"]
    assert client.get("/api/appearance").json() == {"appearance": "light", "accent": "purple"}
    assert "#c795ff" in client.get("/api/appearance/icon.svg").text


def test_storage_capacity_requires_a_verified_mount_and_never_accepts_a_browser_path(tmp_path, monkeypatch):
    class DB:
        def execute(self, _query):
            return [("deployment",)]

    @contextmanager
    def db():
        yield DB()

    deployments = SimpleNamespace(store=SimpleNamespace(db=db))
    service = {"volumes": [{"type": "bind", "source": str(tmp_path), "target": "/data"}]}
    payload = {"apps": ["sonarr"], "compose": {"services": {"sonarr": service}}}
    monkeypatch.setattr("stackarr.overview.load_receipt", lambda *_: payload)
    monkeypatch.setattr("stackarr.overview.inspect_container", lambda *_: {})
    monkeypatch.setattr("stackarr.overview.app_project", lambda *_: "project")
    monkeypatch.setattr("stackarr.overview.differences", lambda *_: [])
    result = owned_storage(deployments)
    assert result["available"] and result["total_gb"] > 0 and result["free_gb"] >= 0
    monkeypatch.setattr("stackarr.overview.differences", lambda *_: ["mount changed"])
    assert owned_storage(deployments)["available"] is False
