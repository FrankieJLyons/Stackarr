import json

import httpx
import pytest

from stackarr.config import Config
from stackarr.indexers import Source, apply, public, review
from stackarr.store import Conflict, Store


@pytest.fixture
def source_store(tmp_path):
    store = Store(tmp_path)
    config = Config()
    config.integrations["prowlarr"].enabled = True
    config.integrations["prowlarr"].url = "http://prowlarr.example"
    store.save(config, 1, {"prowlarr": {"api_key": "synthetic-controller-key"}})
    return store


async def test_source_is_reviewed_tested_secret_and_duplicate_safe(source_store):
    rows, writes = [], []

    def respond(request):
        assert request.headers["X-Api-Key"] == "synthetic-controller-key" and request.url.host == "prowlarr.example"
        if request.url.path.endswith("/schema"):
            return httpx.Response(200, json=[{"name": "Generic Torznab", "implementation": "Torznab", "definitionName": "Torznab", "configContract": "TorznabSettings", "protocol": "torrent", "fields": [{"name": name} for name in ("baseUrl", "apiPath", "apiKey")]}])
        if request.url.path.endswith("/appprofile"):
            return httpx.Response(200, json=[{"id": 1}])
        if request.method == "GET":
            return httpx.Response(200, json=rows)
        writes.append(request.url.path)
        if not request.url.path.endswith("/test"):
            rows.append(json.loads(request.content))
            raise httpx.ReadError("synthetic lost create response")
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(respond)
    source = Source(name="My chosen source", feed_url="http://fixture.example/torznab/api", api_key="fixture-provider")
    plan = await review(source_store, source, transport)
    assert "fixture-provider" not in json.dumps(public(plan))
    assert not rows and not writes
    with pytest.raises(httpx.ReadError):
        await apply(source_store, plan, transport)
    repeat = await review(source_store, source, transport)
    assert repeat["exists"] and (await apply(source_store, repeat, transport))["state"] == "existing"
    assert writes == ["/api/v1/indexer/test", "/api/v1/indexer"] and len(rows) == 1
    revision, config = source_store.config()
    source_store.save(config, revision)
    with pytest.raises(Conflict):
        await apply(source_store, repeat, transport)


@pytest.mark.parametrize("url", ["http://169.254.169.254/api", "file:///secret", "https://provider.example/api?apikey=private", "https://user:private@provider.example/api"])
async def test_invalid_source_addresses_are_rejected_before_contact(source_store, url):
    calls = []
    with pytest.raises(ValueError):
        await review(source_store, Source(name="Fixture", feed_url=url), httpx.MockTransport(lambda request: calls.append(request)))
    assert not calls
