import httpx
import pytest

from stackarr.config import Config, Integration
from stackarr.installer import compose_plan
from stackarr.integrations import IntegrationError, collect
from stackarr.onboarding import SetupDraft, plan


def test_seerr_upgrade_is_optional_and_does_not_mutate_input():
    legacy = Config().model_dump()
    legacy["version"] = 2
    legacy["integrations"].pop("seerr")
    legacy["dashboard"]["order"].remove("seerr")
    migrated = Config.model_validate(legacy)
    assert migrated.version == 3 and not migrated.integrations["seerr"].enabled
    assert "seerr" not in legacy["integrations"]
    assert "seerr" not in compose_plan(migrated)["compose"]["services"]


def test_seerr_only_plan_needs_no_media_mount():
    result = plan(SetupDraft(apps=["seerr"]))
    service = result["plan"]["compose"]["services"]["seerr"]
    assert service["init"] and service["cap_drop"] == ["ALL"]
    assert service["volumes"] == [{"type": "volume", "source": "seerr-config", "target": "/app/config"}]


@pytest.mark.asyncio
async def test_seerr_reads_counts_without_mutations():
    def response(request):
        assert request.method == "GET"
        assert request.headers["X-Api-Key"] == "synthetic-key"
        if request.url.path.endswith("/status"):
            assert request.url.params["checkUpdateAvailable"] == "false"
            return httpx.Response(200, json={"version": "synthetic"})
        assert request.url.path == "/api/v1/request/count"
        return httpx.Response(200, json={"total": 2, "pending": 1, "approved": 1, "declined": 0, "processing": 1, "available": 0})

    tables = await collect("seerr", Integration(url="https://seerr.example"), {"api_key": "synthetic-key"}, httpx.MockTransport(response))
    assert tables["requests"][0]["state"] == "2"
    assert tables["health"][0]["state"] == "connected"


@pytest.mark.parametrize("completed,valid", [(2, True), ("bad", False), (-1, False)])
async def test_seerr_v35_completed_requests_stay_distinct_from_available(completed, valid):
    def response(request):
        return httpx.Response(200, json={"version": "3.5.0"} if request.url.path.endswith("/status") else
                              {"total": 2, "pending": 0, "approved": 0, "declined": 0, "processing": 0, "available": 0, "completed": completed})

    if not valid:
        with pytest.raises(IntegrationError):
            await collect("seerr", Integration(url="https://seerr.example"), {"api_key": "fixture"}, httpx.MockTransport(response))
        return
    tables = await collect("seerr", Integration(url="https://seerr.example"), {"api_key": "fixture"}, httpx.MockTransport(response))
    counts = {row["title"]: row["state"] for row in tables["requests"]}
    assert counts["Completed"] == "2" and counts["Available"] == "0"


@pytest.mark.parametrize("code,payload", [(401, {}), (200, {"pending": "bad"})])
@pytest.mark.asyncio
async def test_seerr_rejects_auth_and_malformed_counts(code, payload):
    def response(request):
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"version": "synthetic"})
        return httpx.Response(code, json=payload)

    with pytest.raises(IntegrationError):
        await collect("seerr", Integration(url="https://seerr.example"), {"api_key": "synthetic"}, httpx.MockTransport(response))
