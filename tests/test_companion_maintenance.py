from types import SimpleNamespace

import httpx
import pytest

from stackarr.companion_maintenance import checkpoint, version
from stackarr.companions import Companions
from stackarr.store import Store
from stackarr.updates import Updates, catalog, protected_state


@pytest.mark.asyncio
@pytest.mark.parametrize("app,body,expected", [
    ("tautulli", {"response": {"data": {"tautulli_version": "v2.18.2"}}}, "v2.18.2"),
    ("cleanuparr", {"application": {"version": "2.10.11.0"}}, "2.10.11"),
])
async def test_companion_versions_use_running_release_not_image_branch(monkeypatch, app, body, expected):
    async def reply(*args):
        return body
    monkeypatch.setattr("stackarr.companion_maintenance.request", reply)
    assert await version(app, "http://fixture", {"api_key": "fixture"}) == expected


@pytest.mark.asyncio
async def test_cleanup_checkpoint_includes_safety_flags_and_saved_connections(monkeypatch):
    seen = []
    async def reply(base, secret, path):
        seen.append(path)
        return {"fixture": path}
    monkeypatch.setattr("stackarr.companion_maintenance.request", reply)
    value = await checkpoint("cleanuparr", "http://fixture", {"api_key": "fixture"})
    assert set(value) == {"general", "queue_cleaner", "download_cleaner", "malware_blocker", "seeker", "blacklist_sync", "sonarr", "radarr", "download_client"}
    assert len(seen) == 9 and all(path.startswith("/api/configuration/") for path in seen)


@pytest.mark.asyncio
async def test_kuma_version_is_excluded_from_stable_monitor_checkpoint(monkeypatch):
    state = {"version": "2.5.5", "monitors": [{"id": 1, "name": "Original monitor"}], "keys": [{"id": 7}]}
    monkeypatch.setattr("stackarr.companion_maintenance.kuma_checkpoint", lambda *_: state.copy())
    before = await checkpoint("kuma", "http://fixture", {})
    state["version"] = "2.5.6"
    assert await checkpoint("kuma", "http://fixture", {}) == before
    state["monitors"] = []
    assert await checkpoint("kuma", "http://fixture", {}) != before


@pytest.mark.asyncio
async def test_cleanup_new_errored_torrent_option_accepts_only_reviewed_inactive_default(monkeypatch):
    extra = None
    async def reply(base, secret, path):
        return {"errored": extra.copy()} if path.endswith("/queue_cleaner") and extra is not None else {}
    monkeypatch.setattr("stackarr.companion_maintenance.request", reply)
    before = await checkpoint("cleanuparr", "http://fixture", {})
    extra = {"maxStrikes": 0, "ignorePrivate": False, "deletePrivate": False, "changeCategory": False}
    assert await checkpoint("cleanuparr", "http://fixture", {}) == before
    extra["maxStrikes"] = 1
    assert await checkpoint("cleanuparr", "http://fixture", {}) != before
    extra["maxStrikes"], extra["deletePrivate"] = 0, True
    assert await checkpoint("cleanuparr", "http://fixture", {}) != before


def test_all_nine_app_update_candidates_are_immutable():
    values = catalog()["apps"]
    assert set(values) == {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr", "tautulli", "kuma", "cleanuparr"}
    assert all("@sha256:" in row["image"] for row in values.values())


@pytest.mark.asyncio
async def test_seerr_checkpoint_protects_actual_library_paths_and_paginates_users(monkeypatch):
    directory = "/data/media/tv"
    seen = []
    def reply(request):
        assert request.method == "GET"
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/user"):
            skip = int(request.url.params["skip"])
            return httpx.Response(200, json={"results": [{"id": n, "email": f"fixture{n}@example.invalid", "permissions": 2} for n in range(skip, min(skip + 100, 101))]})
        if path.endswith("/request"):
            return httpx.Response(200, json={"results": [{"id": 7, "status": 2, "requestedBy": {"id": 1}, "media": {"id": 3, "tmdbId": 123}}]})
        if path.endswith("/plex"):
            return httpx.Response(200, json={"machineId": "fresh-fixture", "libraries": []})
        if path.endswith("/main"):
            return httpx.Response(200, json={"mediaServerType": 1, "mediaServerLogin": True})
        return httpx.Response(200, json=[{"id": 1, "activeDirectory": directory}])
    client = httpx.AsyncClient
    monkeypatch.setattr("stackarr.updates.httpx.AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(reply), **kwargs))
    payload = {"compose": {"services": {"seerr": {"ports": [{"published": "43500"}]}}}}
    before = await protected_state(payload, "seerr", {"api_key": "fixture"})
    assert len(before["users"]) == 101 and any("skip=100" in value for value in seen)
    assert before["sonarr"][0]["activeDirectory"] == directory
    assert before["requests"][0]["requestedBy"] == 1
    directory = "/unexpected/path"
    assert await protected_state(payload, "seerr", {"api_key": "fixture"}) != before


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["mediaServerLogin", "newPlexLogin", "localLogin", "mediaServerType", "defaultPermissions", "plexId"])
async def test_seerr_checkpoint_detects_changed_plex_identity_or_signin_settings(monkeypatch, changed):
    main = {"mediaServerType": 1, "mediaServerLogin": True, "newPlexLogin": False, "localLogin": False, "defaultPermissions": 32}
    user = {"id": 1, "plexId": 123, "plexUsername": "fixture", "userType": 1, "permissions": 2}
    def reply(request):
        assert request.method == "GET"
        path = request.url.path
        if path.endswith("/main"):
            value = main.copy()
        elif path.endswith("/user"):
            value = {"results": [user.copy()]}
        elif path.endswith("/request"):
            value = {"results": []}
        elif path.endswith("/plex"):
            value = {"machineId": "isolated-fixture", "libraries": [{"id": "1", "enabled": True}]}
        else:
            value = []
        return httpx.Response(200, json=value)
    client = httpx.AsyncClient
    monkeypatch.setattr("stackarr.updates.httpx.AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(reply), **kwargs))
    payload = {"compose": {"services": {"seerr": {"ports": [{"published": "43500"}]}}}}
    before = await protected_state(payload, "seerr", {"api_key": "fixture"})
    if changed == "plexId":
        user[changed] = 456
    else:
        main[changed] = not main[changed] if isinstance(main[changed], bool) else 99
    assert await protected_state(payload, "seerr", {"api_key": "fixture"}) != before


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["elevated", "removed", "revived", "identity"])
async def test_seerr_checkpoint_detects_changed_invited_access_and_revived_user(monkeypatch, change):
    owner = {"id": 1, "userType": 1, "permissions": 2, "plexId": 101}
    invited = {"id": 7, "userType": 1, "permissions": 32, "plexId": 107}
    users = [owner.copy()] if change == "revived" else [owner.copy(), invited.copy()]
    def reply(request):
        assert request.method == "GET"
        path = request.url.path
        if path.endswith("/user"):
            value = {"results": [row.copy() for row in users]}
        elif path.endswith("/request"):
            value = {"results": []}
        elif path.endswith("/main"):
            value = {"defaultPermissions": 32, "newPlexLogin": False}
        elif path.endswith("/plex"):
            value = {"machineId": "isolated-fixture", "libraries": []}
        else:
            value = []
        return httpx.Response(200, json=value)
    client = httpx.AsyncClient
    monkeypatch.setattr("stackarr.updates.httpx.AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(reply), **kwargs))
    payload = {"compose": {"services": {"seerr": {"ports": [{"published": "43500"}]}}}}
    before = await protected_state(payload, "seerr", {"api_key": "fixture"})
    if change == "elevated":
        users[1]["permissions"] = 2
    elif change == "removed":
        users.pop()
    elif change == "revived":
        users.append(invited.copy())
    else:
        users[1].update(userType=3, plexId=None)
    after = await protected_state(payload, "seerr", {"api_key": "fixture"})
    assert after != before and after["users"][0] == before["users"][0]


def test_candidate_login_uses_reviewed_image_recipe_before_receipt_commit(tmp_path, monkeypatch):
    companions = Companions(SimpleNamespace(store=Store(tmp_path)))
    candidate = {"compose": {"services": {"cleanuparr": {"image": "approved-candidate"}}}}
    seen = []
    def connections(identity, payload=None):
        seen.append(payload)
        return {"apps": {"cleanuparr": {"port": 1234, "credential": {"api_key": "fixture"}}}}
    monkeypatch.setattr(companions, "connections", connections)
    monkeypatch.setattr(companions, "state", lambda _: {"apps": {"cleanuparr": {"username": "fixture", "password": "fixture"}}})
    monkeypatch.setattr(companions, "client", lambda _: httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"tokens": {"accessToken": "fixture"}}))))
    assert companions.login("a" * 32, "cleanuparr", candidate)["login"]["username"] == "fixture"
    assert seen == [candidate]


def test_legacy_seerr_runs_keep_their_recorded_shape_but_new_runs_protect_plex_login(tmp_path, monkeypatch):
    service = Updates(SimpleNamespace(store=Store(tmp_path)))
    async def protected(*args):
        return {"sonarr": [], "radarr": [], "plex": {}, "requests": [],
                "users": [{"id": 1, "plexId": 123, "plexUsername": "fixture"}],
                "authentication": {"mediaServerLogin": True}}
    monkeypatch.setattr("stackarr.updates.protected_state", protected)
    current = service.protected({}, "seerr", {"_protected_version": 2})
    assert current["authentication"]["mediaServerLogin"] and current["users"][0]["plexId"] == 123
    legacy = service.protected({}, "seerr", {})
    assert "authentication" not in legacy and legacy["users"] == [{"id": 1}]


def test_seerr_background_scan_cursor_does_not_hide_changed_libraries_or_login(tmp_path, monkeypatch):
    service = Updates(SimpleNamespace(store=Store(tmp_path)))
    state = {"scan": 100, "enabled": True, "login": True}
    async def protected(*args):
        return {"users": [], "authentication": {"mediaServerLogin": state["login"]},
                "plex": {"libraries": [{"id": "2", "enabled": state["enabled"], "lastScan": state["scan"]}]}}
    monkeypatch.setattr("stackarr.updates.protected_state", protected)
    original = service.protected({}, "seerr", {"_protected_version": 3})
    state["scan"] += 1
    assert service.protected({}, "seerr", {"_protected_version": 3}) == original
    assert service.protected({}, "seerr", {"_protected_version": 2})["plex"]["libraries"][0]["lastScan"] == 101
    state["enabled"] = False
    assert service.protected({}, "seerr", {"_protected_version": 3}) != original
    state["enabled"], state["login"] = True, False
    assert service.protected({}, "seerr", {"_protected_version": 3}) != original
