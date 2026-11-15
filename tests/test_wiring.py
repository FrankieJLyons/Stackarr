import httpx
import pytest

from stackarr.config import Config
from stackarr.store import Store
from stackarr.wiring import WiringError, apply_plan, build_plan, public_plan


@pytest.fixture
def wired_store(tmp_path):
    store = Store(tmp_path)
    data = Config().model_dump()
    for key, url in (("sonarr", "https://sonarr.example"), ("radarr", "https://radarr.example"),
                     ("prowlarr", "https://prowlarr.example"), ("qbittorrent", "https://qbit.example")):
        data["integrations"][key].update(enabled=True, url=url)
    store.save(Config.model_validate(data), 1, {key: {"api_key": f"{key}-synthetic-key"} for key in ("sonarr", "radarr", "prowlarr")})
    store.save(Config.model_validate(data), 2, {"qbittorrent": {"username": "synthetic", "password": "synthetic-password"}})
    return store


def response(request):
    path = request.url.path
    if path.endswith("/schema"):
        implementation = "QBittorrent" if "sonarr" in request.url.host else "Radarr"
        if "prowlarr" in request.url.host:
            implementation = "Sonarr"
        fields = [{"name": n} for n in ("host", "port", "username", "password", "category", "baseUrl", "apiKey")]
        return httpx.Response(200, json=[{"implementation": implementation, "configContract": "synthetic", "fields": fields}])
    if request.method == "GET":
        return httpx.Response(200, json=[])
    assert request.method == "POST"
    return httpx.Response(200, json={"ok": True})


@pytest.mark.asyncio
async def test_wiring_preview_is_explicit_and_does_not_delete(wired_store):
    plan = await build_plan(wired_store, httpx.MockTransport(response))
    assert plan["revision"] == wired_store.config()[0]
    assert all(change["kind"] in ("download client", "application") for change in plan["changes"])
    reviewed = public_plan(plan)
    rendered = str(reviewed)
    assert "synthetic-password" not in rendered
    assert "synthetic-key" not in rendered
    assert "payload" not in rendered
    assert all(change["action"].startswith("create") for change in reviewed["changes"])


@pytest.mark.asyncio
async def test_wiring_apply_rechecks_revision(wired_store):
    plan = await build_plan(wired_store, httpx.MockTransport(response))
    data = wired_store.config()[1].model_dump()
    wired_store.save(Config.model_validate(data), plan["revision"])
    with pytest.raises(WiringError, match="Settings changed"):
        await apply_plan(wired_store, plan, httpx.MockTransport(response))


@pytest.mark.asyncio
async def test_real_arr_category_field_names(wired_store):
    def schemas(request):
        if request.url.path.endswith("/schema"):
            if "prowlarr" in request.url.host:
                return response(request)
            category = "tvCategory" if "sonarr" in request.url.host else "movieCategory"
            return httpx.Response(200, json=[{"implementation": "QBittorrent", "configContract": "QBittorrentSettings",
                "fields": [{"name": n} for n in ("host", "port", "username", "password", category)]}])
        return httpx.Response(200, json=[])

    plan = await build_plan(wired_store, httpx.MockTransport(schemas))
    downloads = [c for c in plan["changes"] if c["kind"] == "download client"]
    assert len(downloads) == 2
    for change in downloads:
        field = "tvCategory" if change["target"] == "sonarr" else "movieCategory"
        assert next(f["value"] for f in change["payload"]["fields"] if f["name"] == field) == change["target"]
