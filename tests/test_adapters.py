import httpx
import pytest

from stackarr.adapters import ADAPTERS, capabilities, require_write
from stackarr.config import APP_IDS, Config
from stackarr.integrations import Collector
from stackarr.store import Store


def test_catalog_has_explicit_capabilities():
    assert set(capabilities()) == set(APP_IDS)
    assert capabilities()["cleanuparr"]["status"] == "preview"
    assert capabilities()["qbittorrent"]["tables"] == ("downloads",)
    for key in APP_IDS:
        with pytest.raises(ValueError):
            require_write(key, "delete-media")
    require_write("sonarr", "download-client.create")
    with pytest.raises(ValueError):
        require_write("qbittorrent", "download-client.create")


@pytest.mark.asyncio
async def test_cleanup_monitoring_only_reads_safety_settings(tmp_path):
    store = Store(tmp_path)
    data = Config().model_dump()
    data["integrations"]["cleanuparr"].update(enabled=True, url="https://example.test")
    store.save(Config.model_validate(data), 1, {"cleanuparr": {"api_key": "synthetic-private-key"}})

    paths = []
    def read_only(request):
        assert request.method == "GET"
        assert request.headers["X-Api-Key"] == "synthetic-private-key"
        paths.append(request.url.path)
        return httpx.Response(200, json={"dryRun": True, "enabled": False, "searchEnabled": False, "proactiveSearchEnabled": False})

    collector = Collector(store, httpx.MockTransport(read_only))
    await collector.refresh()
    row = collector.view()["integrations"][0]
    assert row["state"] == "ready"
    assert len(paths) == 6 and all(path.startswith("/api/configuration/") for path in paths)
    assert row["capabilities"] == list(ADAPTERS["cleanuparr"].tables)
    assert row["error"] is None
