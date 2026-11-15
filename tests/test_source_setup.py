"""Source diagnostics use synthetic transports; no real source or media is used."""

import json

import httpx
import pytest

from stackarr.config import Config
from stackarr.indexers import (
    ProviderSource,
    SourceCheck,
    apply,
    catalog,
    public,
    review_provider,
    status,
    validate,
)
from stackarr.store import Conflict, Store


@pytest.fixture
def source_store(tmp_path):
    store = Store(tmp_path)
    config = Config()
    config.integrations["prowlarr"].enabled = True
    config.integrations["prowlarr"].url = "http://prowlarr.example"
    store.save(config, 1, {"prowlarr": {"api_key": "synthetic-controller-key"}})
    return store


def template(**changes):
    value = {"name": "Fixture provider", "implementation": "Cardigann", "definitionName": "fixture",
             "configContract": "CardigannSettings", "protocol": "torrent", "privacy": "private",
             "infoLink": "http://private.example/secret", "description": "<img src=x onerror=secret>",
             "fields": [{"name": "baseUrl", "value": "http://private.example", "type": "text"},
                        {"name": "definitionFile", "value": "fixture", "hidden": "hidden"},
                        {"name": "apiKey", "type": "password", "value": "synthetic-old-secret", "required": True,
                         "label": "API Key", "helpText": "http://internal.example?secret=fixture"},
                        {"name": "minimumSeeders", "type": "number", "advanced": True, "value": 1}]}
    value.update(changes)
    return value


async def test_catalog_projects_only_safe_schema_and_marks_complex_forms(source_store):
    schemas = [template(), template(name="Usenet", protocol="usenet"),
               template(name="Captcha", fields=[{"name": "captcha", "type": "captcha"}]),
               template(name="Dynamic", fields=[{"name": "option", "type": "select", "selectOptionsProviderAction": "authenticate"}])]
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=schemas))
    result = await catalog(source_store, transport)
    selected = next(row for row in result["providers"] if row["name"] == "Fixture provider")
    assert selected["supported"] is True
    assert selected["fields"] == [{"name": "apiKey", "label": "API Key", "type": "password",
                                   "required": True, "private": True,
                                   "help": "Use this source's account details. These are sent only to Prowlarr for its source test and save."}]
    assert all(not row["supported"] and row["fields"] == [] for row in result["providers"] if row is not selected)
    encoded = json.dumps(result)
    assert all(value not in encoded for value in ("synthetic-old-secret", "private.example", "internal.example", "img src", "infoLink", "value"))


async def test_native_prowlarr_textboxes_and_advertised_address_choices_are_supported(source_store):
    native = template(indexerUrls=["http://fixture.example/provider"])
    native["fields"] = [
        {"name": "baseUrl", "type": "select", "hidden": None, "value": None, "selectOptionsProviderAction": "getUrls"},
        {"name": "definitionFile", "hidden": "hidden", "value": "fixture"},
        {"name": "extraFieldData.username", "type": "textbox", "hidden": None, "advanced": False, "label": "Username"},
        {"name": "extraFieldData.password", "type": "password", "hidden": None, "advanced": False, "label": "Password"},
        {"name": "torrentBaseSettings.seedRatio", "type": "number", "hidden": None, "advanced": False, "value": None},
        {"name": "vipExpiration", "type": "textbox", "hidden": None, "advanced": False, "value": "private-expiration"}]
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/schema"):
            return httpx.Response(200, json=[native])
        return httpx.Response(200, json=[{"id": 1}] if request.url.path.endswith("/appprofile") else [])

    transport = httpx.MockTransport(respond)
    provider = (await catalog(source_store, transport))["providers"][0]
    assert provider["supported"] is True
    assert [field["name"] for field in provider["fields"]] == ["extraFieldData.username", "extraFieldData.password"]
    assert "fixture.example" not in json.dumps(provider) and "private-expiration" not in json.dumps(provider)
    proposal = await review_provider(source_store, {"provider_id": provider["id"], "name": "Fixture", "fields": {
        "extraFieldData.username": "fixture-user", "extraFieldData.password": "fixture-password"}}, transport)
    fields = {field["name"]: field.get("value") for field in proposal["payload"]["fields"]}
    assert fields["baseUrl"] == "http://fixture.example/provider" and fields["extraFieldData.password"] == "fixture-password"
    assert all(method == "GET" for method, _ in calls)


async def test_native_custom_feed_and_missing_address_use_explicit_advanced_fallback(source_store):
    templates = [template(name="Generic Torznab"), template(fields=[{"name": "baseUrl", "type": "textbox"}])]
    result = await catalog(source_store, httpx.MockTransport(lambda _: httpx.Response(200, json=templates)))
    assert all(row["supported"] is False for row in result["providers"])


async def test_provider_review_is_read_only_and_apply_tests_only_new_provider(source_store):
    schemas, rows, calls = [template()], [], []

    def respond(request):
        calls.append((request.method, request.url.path))
        assert request.url.host == "prowlarr.example"
        if request.url.path.endswith("/schema"):
            return httpx.Response(200, json=schemas)
        if request.url.path.endswith("/appprofile"):
            return httpx.Response(200, json=[{"id": 7}])
        if request.method == "GET":
            return httpx.Response(200, json=rows)
        payload = json.loads(request.content)
        fields = {field["name"]: field.get("value") for field in payload["fields"]}
        assert fields["apiKey"] == "synthetic-new-secret" and fields["baseUrl"] == "http://private.example"
        assert payload["appProfileId"] == 7
        if not request.url.path.endswith("/test"):
            rows.append(payload)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(respond)
    provider = (await catalog(source_store, transport))["providers"][0]
    plan = await review_provider(source_store, {"provider_id": provider["id"], "name": "My source",
                                               "fields": {"apiKey": "synthetic-new-secret"}}, transport)
    assert all(method == "GET" for method, _ in calls)
    assert schemas == [template()]
    assert "synthetic-new-secret" not in json.dumps(public(plan)) and "private.example" not in json.dumps(public(plan))
    assert (await apply(source_store, plan, transport))["state"] == "connected"
    assert calls[-2:] == [("POST", "/api/v1/indexer/test"), ("POST", "/api/v1/indexer")]
    assert (await apply(source_store, plan, transport))["state"] == "existing"
    revision, config = source_store.config()
    source_store.save(config, revision)
    with pytest.raises(Conflict):
        await apply(source_store, plan, transport)


@pytest.mark.parametrize("fields", [{}, {"apiKey": "fixture", "baseUrl": "http://169.254.169.254"},
                                    {"apiKey": "fixture\nsecret"}, {"apiKey": True}])
async def test_provider_review_rejects_missing_injected_or_invalid_fields(source_store, fields):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=[template()]))
    provider = (await catalog(source_store, transport))["providers"][0]
    with pytest.raises(ValueError):
        await review_provider(source_store, {"provider_id": provider["id"], "name": "Fixture", "fields": fields}, transport)


def configured(source_id=1, **changes):
    value = {"id": source_id, "name": f"Fixture {source_id}", "enable": True, "implementation": "Torznab",
             "fields": [{"name": "apiKey", "value": "synthetic-provider-secret"}],
             "capabilities": {"categories": [{"id": 2000}, {"id": 5000}]}}
    value.update(changes)
    return value


def diagnostics_transport(rows, *, releases=None, test_status=200, history_state="success", history_available=True):
    calls, searched = [], set()

    def respond(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        assert request.url.host == "prowlarr.example"
        if request.url.path.endswith("/indexer/test"):
            return httpx.Response(test_status, json=[] if test_status == 200 else [{"errorMessage": "Invalid credentials synthetic-provider-secret http://internal.example"}])
        if request.url.path.endswith("/indexer"):
            return httpx.Response(200, json=rows)
        source_id = int(request.url.params["indexerIds"])
        if request.url.path.endswith("/search"):
            assert request.method == "GET" and request.url.params["limit"] == "20"
            searched.add(source_id)
            return httpx.Response(200, json=releases or [])
        if request.url.path.endswith("/history"):
            if not history_available:
                return httpx.Response(503, text="synthetic-provider-secret")
            records = [{"id": 10, "indexerId": source_id, "eventType": "indexerQuery", "successful": True}]
            if source_id in searched and history_state != "missing":
                records.append({"id": 11, "indexerId": source_id, "eventType": "indexerQuery",
                                "successful": history_state == "success",
                                "data": {"Query": "Fixture title", "QueryType": "search", "Categories": "2000",
                                         "Url": "http://internal.example?apikey=synthetic-provider-secret"}})
            return httpx.Response(200, json={"records": records})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    return httpx.MockTransport(respond), calls


async def test_validation_proves_empty_search_with_new_successful_history(source_store):
    transport, calls = diagnostics_transport([configured()])
    result = await validate(source_store, {"query": " Fixture title ", "media_type": "movie"}, transport)
    assert result["state"] == "no-matches" and result["sources"][0]["search"] == "no-matches"
    assert result["sources"][0]["authentication"] == "passed" and result["sources"][0]["result_count"] == 0
    assert result["sharing"]["sources"] == [{"name": "Fixture 1", "enabled": True, "id": 1}]
    assert all(method == "GET" or path == "/api/v1/indexer/test" for method, path, _ in calls)
    encoded = json.dumps(result)
    assert all(value not in encoded for value in ("synthetic-provider-secret", "internal.example", "Fixture title", "QueryType"))


@pytest.mark.parametrize("history_state,history_available,state", [("failed", True, "search-failed"),
                                                                 ("missing", True, "unverified"),
                                                                 ("success", False, "unverified")])
async def test_http_200_empty_cannot_hide_failed_or_unobserved_search(source_store, history_state, history_available, state):
    transport, _ = diagnostics_transport([configured()], history_state=history_state, history_available=history_available)
    result = await validate(source_store, SourceCheck(query="Fixture title", media_type="movie"), transport)
    assert result["state"] == "needs-attention" and result["sources"][0]["state"] == state
    assert result["sources"][0]["result_count"] is None


async def test_results_are_counted_but_never_project_release_urls(source_store):
    transport, _ = diagnostics_transport([configured()], releases=[{"indexerId": 1, "title": "Fixture title", "downloadUrl": "http://private.example/secret"}])
    result = await validate(source_store, {"query": "Fixture title", "media_type": "tv"}, transport)
    assert result["state"] == "results" and result["sources"][0]["result_count"] == 1
    assert "Fixture title" not in json.dumps(result) and "private.example" not in json.dumps(result)


async def test_results_without_category_capabilities_remain_unverified(source_store):
    transport, _ = diagnostics_transport([configured(capabilities=None)], releases=[{"indexerId": 1}])
    result = await validate(source_store, {"query": "Fixture title", "media_type": "movie"}, transport)
    assert result["state"] == "needs-attention"
    source = result["sources"][0]
    assert source["state"] == "unverified" and source["categories"] == "unknown" and source["result_count"] == 1
    assert source["search"] == "results" and "categories could not be verified" in source["detail"]


@pytest.mark.parametrize("payload", [["unexpected"], {"records": []}, [None]])
async def test_malformed_catalog_or_configured_rows_are_safe_failures(source_store, payload):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(ValueError):
        await catalog(source_store, transport)
    with pytest.raises(ValueError):
        await validate(source_store, {"query": "Fixture title", "media_type": "movie"}, transport)


async def test_authentication_failure_has_fixed_guidance_and_never_searches(source_store):
    transport, calls = diagnostics_transport([configured()], test_status=400)
    result = await validate(source_store, {"query": "Fixture title", "media_type": "movie"}, transport)
    assert result["sources"][0]["state"] == "authentication-failed"
    assert result["sources"][0]["authentication"] == "failed"
    assert all(not path.endswith("/search") for _, path, _ in calls)
    assert "synthetic-provider-secret" not in json.dumps(result) and "internal.example" not in json.dumps(result)


async def test_wrong_categories_disabled_sources_and_limit_are_explicit(source_store):
    rows = [configured(1, capabilities={"categories": [{"id": 5000}]}), configured(2, enable=False),
            configured(3), configured(4), configured(5)]
    transport, calls = diagnostics_transport(rows, releases=[{"indexerId": 3}, {"indexerId": 4}])
    result = await validate(source_store, {"query": "Fixture title", "media_type": "movie"}, transport)
    assert [row["state"] for row in result["sources"]] == ["category-missing", "disabled", "results", "results", "not-tested"]
    assert result["checked_sources"] == 3 and result["total_enabled"] == 4 and result["limited"] is True
    assert sum(path.endswith("/indexer/test") for _, path, _ in calls) == 2


async def test_no_configured_sources_is_not_a_successful_search(source_store):
    transport, calls = diagnostics_transport([])
    result = await validate(source_store, {"query": "Fixture title", "media_type": "movie"}, transport)
    assert result["state"] == "not-configured" and result["checked_sources"] == 0
    assert all(method == "GET" for method, _, _ in calls)


@pytest.mark.parametrize("query", ["  ", "x", "a\nb", "x" * 121])
def test_diagnostic_query_is_bounded(query):
    with pytest.raises(ValueError):
        SourceCheck(query=query, media_type="movie")


def test_provider_body_is_strict_and_bounded():
    with pytest.raises(ValueError):
        ProviderSource(provider_id="not-a-template", name="Fixture")
    with pytest.raises(ValueError):
        ProviderSource(provider_id="a" * 24, name="Fixture", fields={f"field{index}": "value" for index in range(33)})


@pytest.mark.parametrize("failure", [503, "malformed", "malformed-address"])
async def test_source_status_preserves_other_evidence_when_one_arr_is_unavailable(source_store, failure):
    revision, config = source_store.config()
    for name in ("sonarr", "radarr"):
        config.integrations[name].enabled = True
        config.integrations[name].url = "http://" + name + ".example"
    source_store.save(config, revision, {name: {"api_key": "fixture"} for name in ("sonarr", "radarr")})

    def respond(request):
        if request.url.host == "prowlarr.example":
            return httpx.Response(200, json=[configured()])
        if request.url.host == "sonarr.example":
            if failure == "malformed-address":
                return httpx.Response(200, json=[{"implementation": "Torznab", "fields": [{"name": "baseUrl", "value": 777}]}])
            return httpx.Response(503, text="private error") if failure == 503 else httpx.Response(200, json=None)
        return httpx.Response(200, json=[{"implementation": "Torznab", "fields": [{"name": "baseUrl", "value": "http://prowlarr.example"}]}])

    result = await status(source_store, httpx.MockTransport(respond))
    assert result["sources"] == [{"id": 1, "name": "Fixture 1", "enabled": True}]
    assert result["apps"] == [{"app": "sonarr", "name": "Sonarr", "shared_sources": None, "state": "unavailable"},
                              {"app": "radarr", "name": "Radarr", "shared_sources": 1}]
    assert "private error" not in json.dumps(result)
