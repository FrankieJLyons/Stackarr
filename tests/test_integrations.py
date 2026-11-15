import asyncio
import time

import httpx
import pytest

from stackarr.config import Config, Integration
from stackarr.integrations import Collector, IntegrationError, collect, queue_state, torrent_state
from stackarr.store import Store


def arr_response(request):
    path = request.url.path
    assert request.method == "GET", "Read-only adapter attempted a write"
    if path.endswith("system/status"):
        return httpx.Response(200, json={"version": "synthetic"})
    if path.endswith("health"):
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={"records": [], "totalRecords": 0})


@pytest.mark.parametrize("rows", [[], [{"title": "Synthetic item", "trackedDownloadState": "importPending"}]])
async def test_empty_and_single_arrays_remain_arrays(rows):
    def handler(request):
        if request.url.path.endswith("queue"):
            return httpx.Response(200, json={"records": rows})
        return arr_response(request)

    data = await collect("sonarr", Integration(url="http://sonarr.example"), {}, httpx.MockTransport(handler))
    assert isinstance(data["queue"], list)
    assert len(data["queue"]) == len(rows)


async def test_single_object_instead_of_array_is_explicit_failure():
    def handler(request):
        if request.url.path.endswith("queue"):
            return httpx.Response(200, json={"records": {"title": "Wrong shape"}})
        return arr_response(request)

    with pytest.raises(IntegrationError, match="data shape"):
        await collect("sonarr", Integration(url="http://sonarr.example"), {}, httpx.MockTransport(handler))


@pytest.mark.parametrize("status", [401, 403, 500, 302])
async def test_api_failure_is_not_zero(status):
    with pytest.raises(IntegrationError):
        await collect(
            "radarr",
            Integration(url="http://radarr.example"),
            {},
            httpx.MockTransport(lambda r: httpx.Response(status)),
        )


async def test_bad_json_is_not_zero():
    with pytest.raises(IntegrationError):
        await collect(
            "sonarr",
            Integration(url="http://sonarr.example"),
            {},
            httpx.MockTransport(lambda r: httpx.Response(200, text="<html>proxy error</html>")),
        )


async def test_failure_retains_last_success_without_blanking_other_apps(tmp_path):
    fail = False

    def handler(request):
        if fail and request.url.host == "radarr.example":
            return httpx.Response(503)
        return arr_response(request)

    store = Store(tmp_path)
    config = Config().model_dump()
    for key in ("sonarr", "radarr"):
        config["integrations"][key].update(enabled=True, url=f"http://{key}.example")
    store.save(Config.model_validate(config), 1)
    collector = Collector(store, httpx.MockTransport(handler))
    await collector.refresh()
    original = collector.view()["integrations"][1]["collected_at"]
    fail = True
    await collector.refresh()
    rows = collector.view()["integrations"]
    assert rows[0]["state"] == "ready"
    assert rows[1]["state"] == "unavailable"
    assert rows[1]["collected_at"] == original
    assert rows[1]["tables"] is not None
    assert rows[1]["error"]
    collector.snapshots["radarr"]["collected_at"] = time.time() - 3600
    assert collector.view()["integrations"][1]["stale"]


async def test_absent_apps_never_make_requests(tmp_path):
    store = Store(tmp_path)

    def unexpected(request):
        pytest.fail("Unconfigured app must not be contacted")

    collector = Collector(store, httpx.MockTransport(unexpected))
    await collector.refresh()
    assert collector.view()["integrations"] == []


async def test_configuration_change_discards_inflight_results(tmp_path):
    store = Store(tmp_path)
    config = Config().model_dump()
    config["integrations"]["sonarr"].update(enabled=True, url="https://sonarr.example")
    store.save(Config.model_validate(config), 1)
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        started.set()
        await release.wait()
        return arr_response(request)

    collector = Collector(store, httpx.MockTransport(handler))
    task = asyncio.create_task(collector.refresh())
    await started.wait()
    store.save(Config(), 2)
    release.set()
    await task
    assert collector.view()["integrations"] == []


def test_download_states_are_not_inferred_from_titles():
    assert queue_state({"trackedDownloadState": "importing"}) == "importing"
    assert queue_state({"trackedDownloadState": "importPending"}) == "awaiting import"
    assert queue_state({"trackedDownloadState": "importBlocked"}) == "blocked"
    assert torrent_state("stalledDL") == "stalled"
    assert torrent_state("stalledUP") == "seeding"
    assert torrent_state("downloading") == "downloading"


async def test_qbit_auth_is_only_write():
    def handler(request):
        if request.url.path.endswith("auth/login"):
            assert request.method == "POST"
            return httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=synthetic"})
        assert request.method == "GET"
        return httpx.Response(
            200, json=[{"name": "Synthetic download", "state": "stalledDL", "progress": 0.4}]
        )

    data = await collect(
        "qbittorrent", Integration(url="https://qbit.example"), {}, httpx.MockTransport(handler)
    )
    assert data["downloads"][0]["state"] == "stalled"


async def test_bounded_retries():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("Synthetic failure")

    with pytest.raises(IntegrationError):
        await collect("sonarr", Integration(url="https://sonarr.example"), {}, httpx.MockTransport(handler))
    assert len(calls) == 2


async def test_requested_refresh_waits_for_existing_collection(tmp_path, monkeypatch):
    store = Store(tmp_path)
    data = Config().model_dump()
    data["integrations"]["sonarr"].update(enabled=True, url="https://sonarr.example")
    store.save(Config.model_validate(data), 1)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def controlled(*args):
        calls.append(True)
        started.set()
        await release.wait()
        return {"queue": []}

    monkeypatch.setattr("stackarr.integrations.collect", controlled)
    collector = Collector(store)
    first = asyncio.create_task(collector.refresh())
    await started.wait()
    second = asyncio.create_task(collector.refresh(maintenance=False))
    await asyncio.sleep(0)
    assert not second.done() and len(calls) == 1
    release.set()
    await asyncio.gather(first, second)
    assert len(calls) == 2


async def test_appearance_change_preserves_data_but_credential_change_invalidates_it(tmp_path):
    store = Store(tmp_path)
    data = Config().model_dump()
    data["integrations"]["sonarr"].update(enabled=True, url="https://sonarr.example")
    store.save(Config.model_validate(data), 1)
    collector = Collector(store, httpx.MockTransport(arr_response))
    await collector.refresh()
    original = collector.view()["integrations"][0]
    revision, config = store.config()
    config.dashboard.appearance = "light"
    store.save(config, revision)
    assert collector.view()["integrations"][0]["collected_at"] == original["collected_at"]
    assert collector.view()["integrations"][0]["state"] == "ready"
    revision, config = store.config()
    store.save(config, revision, {"sonarr": {"api_key": "different-synthetic-key"}})
    assert collector.view()["integrations"][0]["state"] == "pending"


async def test_oversized_stream_stops_reading_and_closes_connection(monkeypatch):
    monkeypatch.setattr("stackarr.integrations.RESPONSE_LIMIT", 65536)
    class Stream(httpx.AsyncByteStream):
        read = 0
        closed = False
        async def __aiter__(self):
            for _ in range(100):
                self.read += 1
                yield b"x" * 65536
        async def aclose(self):
            self.closed = True
    stream = Stream()
    with pytest.raises(IntegrationError, match="collection limit"):
        await collect("sonarr", Integration(url="http://fixture.example"), {},
                      httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)))
    assert stream.read == 2 and stream.closed


async def test_stalled_stream_has_total_deadline_and_closes_connection(monkeypatch):
    monkeypatch.setattr("stackarr.integrations.RESPONSE_SECONDS", .01)
    class Stream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            yield b"{"
            await asyncio.Event().wait()
        async def aclose(self):
            self.closed = True
    stream = Stream()
    with pytest.raises(IntegrationError, match="too long"):
        await collect("sonarr", Integration(url="http://fixture.example"), {},
                      httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)))
    assert stream.closed
