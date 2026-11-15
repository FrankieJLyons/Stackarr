import json

import httpx
import pytest
from pydantic import ValidationError

from stackarr import onboarding
from stackarr.bootstrap import BootstrapError, quality_profiles
from stackarr.config import Config
from stackarr.controller import InstallIntent
from stackarr.quality import select_profile
from stackarr.seerr_wiring import build
from stackarr.store import Store


@pytest.mark.parametrize("profile", ["HD-1080p", "Ultra-HD", "SD", "HD-720p"])
def test_draft_saves_exact_request_quality_without_activating_apps(tmp_path, profile):
    store = Store(tmp_path)
    onboarding.initialize(store)
    before = store.config()
    draft = onboarding.SetupDraft(apps=["sonarr", "radarr"], data_root="C:/Alpha Media",
        choices={"sonarr": onboarding.AppChoice(quality_profile=profile),
                 "radarr": onboarding.AppChoice(quality_profile="HD-1080p")})
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=draft))
    resumed = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
    planned = onboarding.plan(resumed)
    assert planned["config"]["integrations"]["sonarr"]["quality_profile"] == profile
    assert planned["config"]["integrations"]["radarr"]["quality_profile"] == "HD-1080p"
    assert {row["app"] for row in planned["storage"]["folders"]} == {"/data/media/tv", "/data/media/movies"}
    assert store.config() == before


@pytest.mark.parametrize("choice", [
    {"apps": ["sonarr"], "choices": {"sonarr": {"quality_profile": "8K"}}},
    {"apps": ["plex"], "choices": {"plex": {"quality_profile": "HD-1080p"}}},
    {"apps": ["sonarr"], "choices": {"sonarr": {"mode": "connect", "quality_profile": "SD"}}},
])
def test_draft_rejects_unknown_quality_or_changes_to_existing_apps(choice):
    with pytest.raises(ValidationError):
        onboarding.SetupDraft.model_validate(choice)


def test_controller_quality_is_bounded_to_selected_arr_apps():
    valid = {"apps": ["sonarr"], "ports": {"sonarr": 28989}, "folder": 0,
             "quality_profiles": {"sonarr": "Ultra-HD"}}
    assert InstallIntent.model_validate(valid).quality_profiles == {"sonarr": "Ultra-HD"}
    for profiles in ({"radarr": "SD"}, {"sonarr": "8K"}, {"plex": "HD-1080p"}):
        with pytest.raises(ValidationError):
            InstallIntent.model_validate({**valid, "quality_profiles": profiles})


@pytest.mark.parametrize("profiles", [[], [{"id": True, "name": "HD-1080p"}],
    [{"id": 1, "name": "HD-1080p"}, {"id": 2, "name": "HD-1080p"}]])
def test_profile_resolution_refuses_missing_ambiguous_or_invalid_profiles(profiles):
    with pytest.raises(ValueError):
        select_profile(profiles, "HD-1080p")


def test_installed_profile_check_is_read_only_and_never_falls_back(monkeypatch):
    calls = []
    profiles = [{"id": 1, "name": "Any"}, {"id": 4, "name": "HD-1080p"}]

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=profiles)

    original_client = httpx.Client
    monkeypatch.setattr("stackarr.bootstrap.httpx.Client", lambda **kwargs:
        original_client(transport=httpx.MockTransport(respond), **kwargs))
    payload = {"apps": ["sonarr"], "config": {"integrations": {"sonarr": {"quality_profile": "HD-1080p"}}},
               "compose": {"services": {"sonarr": {"ports": [{"published": "28989"}]}}}}
    quality_profiles(payload, {"sonarr": {"api_key": "fixture-key"}})
    profiles.pop()
    with pytest.raises(BootstrapError, match="HD-1080p"):
        quality_profiles(payload, {"sonarr": {"api_key": "fixture-key"}})
    assert len(calls) == 2 and all(request.method == "GET" for request in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["HD-1080p", "Ultra-HD", "SD", "HD-720p"])
async def test_seerr_uses_reviewed_profile_even_when_it_is_not_first(tmp_path, profile):
    store = Store(tmp_path)
    config = Config()
    for key in ("sonarr", "seerr"):
        config.integrations[key].enabled = True
        config.integrations[key].url = f"http://{key}.example"
    config.integrations["sonarr"].quality_profile = profile
    store.save(config, 1, {key: {"api_key": "fixture-key"} for key in ("sonarr", "seerr")})
    available = [{"id": 1, "name": "Any"}, {"id": 8, "name": profile}]
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"version": "3.5.0"})
        if request.url.path.endswith("/qualityprofile"):
            return httpx.Response(200, json=available)
        if request.url.path.endswith("/rootfolder"):
            return httpx.Response(200, json=[{"id": 1, "path": "/data/media/tv"}])
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        changes, notices = await build(store, client)
        assert not notices and len(changes) == 1
        assert changes[0]["payload"]["activeProfileId"] == 8
        assert changes[0]["payload"]["activeProfileName"] == profile
        assert changes[0]["payload"]["activeDirectory"] == "/data/media/tv"
        available.pop()
        changes, notices = await build(store, client)
        assert changes == [] and profile in json.dumps(notices)
    assert all(request.method == "GET" for request in calls)
