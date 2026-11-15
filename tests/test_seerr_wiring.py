import json

import httpx
import pytest

from stackarr.config import Config
from stackarr.store import Store
from stackarr.wiring import apply_plan, build_plan, public_plan


@pytest.fixture
def seerr_store(tmp_path):
    store = Store(tmp_path)
    config = Config()
    for key in ("seerr", "sonarr", "radarr"):
        config.integrations[key].enabled = True
        config.integrations[key].url = "http://" + key + ".example"
    store.save(config, 1, {key: {"api_key": "fixture-" + key} for key in ("seerr", "sonarr", "radarr")})
    return store


def upstream(rows, calls, *, lose_response=False, during_test=None):
    def respond(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if request.url.host != "seerr.example":
            target = request.url.host.split(".")[0]
            if path.endswith("/qualityprofile"):
                return httpx.Response(200, json=[{"id": 1, "name": "Existing HD profile"}])
            return httpx.Response(200, json=[{"id": 1, "path": "/data/media/" + ("tv" if target == "sonarr" else "movies")}])
        if path.endswith("/status"):
            return httpx.Response(200, json={"version": "3.5.0"})
        if request.method == "GET":
            return httpx.Response(200, json=rows.get(path, []))
        payload = json.loads(request.content)
        if path.endswith("/test"):
            if during_test:
                during_test()
            return httpx.Response(200, json={"profiles": [{"id": 1, "name": payload["activeProfileName"]}],
                                            "rootFolders": [{"path": payload["activeDirectory"]}]})
        rows[path] = [{"id": 0, **payload}]
        if lose_response:
            raise httpx.ReadError("fixture lost save response")
        return httpx.Response(201, json=rows[path][0])
    return httpx.MockTransport(respond)


async def test_review_explains_profiles_and_tests_before_creating_without_duplicate_writes(seerr_store):
    rows, calls = {}, []
    transport = upstream(rows, calls)
    plan = await build_plan(seerr_store, transport)
    assert len(plan["changes"]) == 2 and not any(method == "POST" for method, _ in calls)
    reviewed = json.dumps(public_plan(plan))
    assert "Existing HD profile" in reviewed and "/data/media/tv" in reviewed and "fixture-seerr" not in reviewed
    assert {row["state"] for row in await apply_plan(seerr_store, plan, transport)} == {"created"}
    posts = [path for method, path in calls if method == "POST"]
    assert posts == ["/api/v1/settings/sonarr/test", "/api/v1/settings/sonarr",
                     "/api/v1/settings/radarr/test", "/api/v1/settings/radarr"]
    assert (await build_plan(seerr_store, transport))["changes"] == []
    assert all(row["state"] == "preserved existing" for row in await apply_plan(seerr_store, plan, transport))
    assert [path for method, path in calls if method == "POST"] == posts


async def test_lost_create_response_preserves_existing_and_settings_race_stops_writes(seerr_store):
    rows, calls = {}, []
    transport = upstream(rows, calls, lose_response=True)
    plan = await build_plan(seerr_store, transport)
    assert all(row["state"].startswith("failed") for row in await apply_plan(seerr_store, plan, transport))
    assert (await build_plan(seerr_store, transport))["changes"] == [] and len(rows) == 2
    rows, calls = {}, []

    def edit():
        revision, config = seerr_store.config()
        seerr_store.save(config, revision)

    transport = upstream(rows, calls, during_test=edit)
    plan = await build_plan(seerr_store, transport)
    result = await apply_plan(seerr_store, plan, transport)
    assert all(row["state"].startswith("failed") for row in result) and not rows
    assert [path for method, path in calls if method == "POST"] == ["/api/v1/settings/sonarr/test"]
