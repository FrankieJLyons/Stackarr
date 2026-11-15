import copy
import json

import httpx
import pytest

from stackarr import onboarding, setup_readiness
from stackarr.config import Config
from stackarr.store import Store
from stackarr.wiring import build_plan, public_plan

NOW = 1000
REQUEST_APPS = ["plex", "seerr", "sonarr", "radarr", "prowlarr", "qbittorrent"]


def draft(apps, **extra):
    return {"revision": 3, "draft": {"apps": apps, "step": 2, "data_root": "/media/library", **extra}}


def configured(apps, *, mode="install"):
    config = Config()
    for key in apps:
        config.integrations[key].enabled = True
        config.integrations[key].url = "http://" + key + ".example"
        config.integrations[key].mode = mode
    return config


def installed(apps, **extra):
    return {"available": True, "operations": [{"id": "a" * 32, "apps": apps,
                                                "updated": NOW - 10, "state": "needs-setup"}], **extra}


def collected(apps, **extra):
    return {"integrations": [{"id": key, "state": "ready", "stale": False,
                              "collected_at": NOW - 5, "attempted_at": NOW - 5, **extra} for key in apps]}


def checkpoint(result, identity):
    return next(row for row in result["checkpoints"] if row["id"] == identity)


def test_empty_journey_has_one_choices_action_and_no_unselected_requirements():
    result = setup_readiness.build(draft([]), Config(), now=NOW)
    assert [row["id"] for row in result["checkpoints"]] == ["choices"]
    assert result["next_action"] == {"id": "choose-apps", "label": "Choose apps", "target": "setup-apps",
                                     "checkpoint_id": "choices"}


def test_plex_only_checks_api_separately_from_playback_and_other_apps():
    result = setup_readiness.build(draft(["plex"]), configured(["plex"]),
                                   deployment=installed(["plex", "seerr", "kuma"]), secret_names=["plex"],
                                   collector=collected(["plex"]), now=NOW)
    assert checkpoint(result, "connection-plex")["state"] == "done"
    assert checkpoint(result, "verification")["state"] == "unknown"
    assert result["next_action"]["id"] == "verification"
    assert result["ready_to_watch"] is False
    assert result["ready_to_request"] is False
    assert all(set(row["apps"]) <= {"plex"} for row in result["checkpoints"])
    assert not any(row["id"] in {"sources", "connections"} for row in result["checkpoints"])


def test_kuma_only_never_requires_media_accounts_sources_or_playback():
    result = setup_readiness.build(draft(["kuma"], data_root=""), configured(["kuma"]),
                                   deployment=installed(["kuma"]), secret_names=["kuma"],
                                   collector=collected(["kuma"]), now=NOW)
    assert [row["id"] for row in result["checkpoints"]] == ["choices", "computer", "installation", "connection-kuma"]
    assert result["summary"] == {"done": 4, "total": 4}
    assert result["next_action"] is None
    assert result["ready_to_watch"] is False


def test_six_app_requests_have_required_configuration_and_unknown_functional_checks():
    source = {"config_revision": 4, "checked_at": NOW - 2, "state": "observed", "enabled_sources": 1,
              "shared_sources": {"sonarr": 1, "radarr": 1}}
    result = setup_readiness.build(draft(REQUEST_APPS), configured(REQUEST_APPS), config_revision=4,
                                   deployment=installed(REQUEST_APPS), secret_names=REQUEST_APPS,
                                   collector=collected(REQUEST_APPS), source_status=source, now=NOW)
    assert checkpoint(result, "sources")["state"] == "done"
    assert "search results still need verification" in checkpoint(result, "sources")["detail"]
    assert checkpoint(result, "connections")["state"] == "unknown"
    assert result["next_action"]["id"] == "wiring-preview"
    assert checkpoint(result, "verification")["state"] == "unknown"
    assert result["ready_to_request"] is False


def test_mixed_existing_and_new_setup_preserves_existing_connection():
    apps = ["plex", "seerr"]
    snapshot = draft(apps, data_root="", choices={"plex": {"mode": "connect", "url": "http://earlier.example"}})
    config = configured(["plex"], mode="connect")
    original = config.model_dump()
    result = setup_readiness.build(snapshot, config, secret_names=["plex"], collector=collected(["plex"]),
                                   deployment=installed(["seerr"]), now=NOW)
    assert config.model_dump() == original
    assert checkpoint(result, "computer")["apps"] == ["seerr"]
    assert checkpoint(result, "installation")["apps"] == ["seerr"]
    assert not any(row["id"] == "storage" for row in result["checkpoints"])
    assert result["next_action"]["id"] == "finish-connecting"
    assert result["next_action"]["app"] == "seerr"


def test_connect_only_omits_host_storage_and_installation():
    snapshot = draft(["plex"], data_root="", choices={"plex": {"mode": "connect", "url": "http://plex.example"}})
    result = setup_readiness.build(snapshot, configured(["plex"], mode="connect"), secret_names=["plex"], now=NOW)
    assert [row["id"] for row in result["checkpoints"]] == ["choices", "connection-plex", "verification"]
    assert result["next_action"]["id"] == "test-connections"
    assert checkpoint(result, "connection-plex")["state"] == "unknown"


@pytest.mark.parametrize("status,action,state", [("running", "check-progress", "in-progress"),
                                                  ("queued", "check-progress", "in-progress"),
                                                  ("failed", "resume-install", "needs-action"),
                                                  ("interrupted", "resume-install", "needs-action"),
                                                  ("ports-blocked", "check-progress", "needs-action")])
def test_installation_failures_and_progress_keep_one_relevant_action(status, action, state):
    deployment = installed(["plex"])
    deployment["operations"][0]["state"] = status
    result = setup_readiness.build(draft(["plex"]), Config(), deployment=deployment, now=NOW)
    assert checkpoint(result, "installation")["state"] == state
    assert result["next_action"]["id"] == action
    assert result["next_action"]["checkpoint_id"] == "installation"


def test_stale_controller_never_recommends_resume_or_claims_current_install_success():
    deployment = installed(["plex"], available=False, status_stale=True, last_checked=NOW - 500)
    deployment["operations"][0]["state"] = "interrupted"
    result = setup_readiness.build(draft(["plex"]), Config(), deployment=deployment, now=NOW)
    assert checkpoint(result, "installation")["state"] == "stale"
    assert checkpoint(result, "installation")["evidence"]["freshness"] == "stale"
    assert result["next_action"]["id"] == "reconnect-installation"


@pytest.mark.parametrize("observation,state", [({"collected_at": NOW - 200, "attempted_at": NOW - 200}, "stale"),
                                               ({"state": "pending", "collected_at": None, "attempted_at": None}, "unknown"),
                                               ({"state": "unavailable", "stale": True}, "needs-action"),
                                               ({"state": "ready", "stale": True}, "stale")])
def test_connection_stale_unknown_and_failed_are_distinct(observation, state):
    result = setup_readiness.build(draft(["plex"]), configured(["plex"]), deployment=installed(["plex"]),
                                   secret_names=["plex"], collector=collected(["plex"], **observation), now=NOW)
    assert checkpoint(result, "connection-plex")["state"] == state
    assert result["next_action"]["id"] == "test-connections"


def test_runtime_and_source_evidence_are_bound_and_expire():
    config = configured(REQUEST_APPS)
    result = setup_readiness.build(draft(REQUEST_APPS), config, config_revision=7,
                                   runtime={"install_apps": ["plex"], "checked_at": NOW, "state": "ready"},
                                   source_status={"config_revision": 6, "checked_at": NOW, "enabled_sources": 5,
                                                  "shared_sources": {"sonarr": 5, "radarr": 5}}, now=NOW)
    assert checkpoint(result, "computer")["state"] == "unknown"
    assert checkpoint(result, "sources")["state"] == "unknown"
    result = setup_readiness.build(draft(["plex"]), Config(), runtime={"install_apps": ["plex"],
                                   "checked_at": NOW - 300, "state": "ready"}, now=NOW)
    assert checkpoint(result, "computer")["state"] == "stale"


def test_navigation_keeps_valid_choices_and_recent_runtime_check():
    snapshot = draft(["plex"], step=0)
    result = setup_readiness.build(snapshot, Config(), deployment={"available": True}, runtime={"draft_revision": 2,
                                   "install_apps": ["plex"], "checked_at": NOW, "state": "ready"}, now=NOW)
    assert checkpoint(result, "choices")["state"] == "done"
    assert checkpoint(result, "computer")["state"] == "done"
    assert result["next_action"]["id"] == "review-install"


def test_same_source_count_cannot_hide_missing_share_for_selected_app():
    result = setup_readiness.build(draft(REQUEST_APPS), Config(), config_revision=1,
                                   source_status={"config_revision": 1, "checked_at": NOW, "enabled_sources": 1,
                                                  "shared_sources": {"sonarr": 2}}, now=NOW)
    assert checkpoint(result, "sources")["state"] == "needs-action"
    assert checkpoint(result, "sources")["action"]["id"] == "wiring-preview"


def test_reviewed_configuration_advances_to_verification_without_certifying_links():
    checks = [{"source": source, "target": target, "state": "reviewed"}
              for target in ("sonarr", "radarr") for source in ("prowlarr", "qbittorrent")]
    checks.extend({"source": target, "target": "seerr", "state": "reviewed"} for target in ("sonarr", "radarr"))
    checks.extend({"source": "plex", "target": target, "state": "reviewed"} for target in ("sonarr", "radarr", "seerr"))
    evidence = {"config_revision": 4, "checked_at": NOW - 5000, "checks": checks}
    source = {"config_revision": 4, "checked_at": NOW, "state": "observed", "enabled_sources": 1,
              "shared_sources": {"sonarr": 1, "radarr": 1}}
    result = setup_readiness.build(draft(REQUEST_APPS), configured(REQUEST_APPS), config_revision=4,
                                   deployment=installed(REQUEST_APPS), secret_names=REQUEST_APPS,
                                   collector=collected(REQUEST_APPS), source_status=source,
                                   wiring_status=evidence, now=NOW)
    assert checkpoint(result, "connections")["state"] == "done"
    assert "functional verification" in checkpoint(result, "connections")["detail"]
    assert result["next_action"]["id"] == "source-validation"
    assert result["next_action"]["media_type"] == "movie"
    verified = {key: {"config_revision": 4, "checked_at": NOW,
                      "source_snapshot": setup_readiness.source_signature(source), "successful": 1,
                      "matching": 1, "failed": 0, "unverified": 0} for key in ("movie", "tv")}
    result = setup_readiness.build(draft(REQUEST_APPS), configured(REQUEST_APPS), config_revision=4,
                                   deployment=installed(REQUEST_APPS), secret_names=REQUEST_APPS,
                                   collector=collected(REQUEST_APPS), source_status=source,
                                   wiring_status=evidence, validation_status=verified, now=NOW)
    assert result["next_action"]["id"] == "verification"
    assert result["ready_to_watch"] is False and result["ready_to_request"] is False
    evidence["config_revision"] = 3
    result = setup_readiness.build(draft(REQUEST_APPS), configured(REQUEST_APPS), config_revision=4,
                                   wiring_status=evidence, now=NOW)
    assert checkpoint(result, "connections")["state"] == "unknown"


def test_seerr_only_requires_request_verification_without_plex_or_import_tasks():
    result = setup_readiness.build(draft(["seerr"], data_root=""), configured(["seerr"]),
                                   deployment=installed(["seerr"]), secret_names=["seerr"],
                                   collector=collected(["seerr"]), now=NOW)
    assert result["next_action"]["id"] == "verification"
    assert checkpoint(result, "verification")["title"] == "Verify requests"
    assert "import" not in checkpoint(result, "verification")["detail"].lower()
    assert checkpoint(result, "verification")["apps"] == ["seerr"]


def test_unavailable_host_offers_reconnect_instead_of_missing_runtime_button():
    result = setup_readiness.build(draft(["plex"]), Config(), deployment={"available": False}, now=NOW)
    assert result["next_action"]["id"] == "reconnect-installation"
    assert result["next_action"]["target"] == "setup-reconnect"
    assert checkpoint(result, "installation")["action"]["id"] == "reconnect-installation"


def test_saved_wiring_review_rejects_skipped_proposals_failed_apply_and_secret_payload(tmp_path):
    store = Store(tmp_path)
    checks = [{"source": "prowlarr", "target": "sonarr", "state": "preserved"},
              {"source": "qbittorrent", "target": "sonarr", "state": "proposed"},
              {"source": "sonarr", "target": "seerr", "state": "unavailable"}]
    change = {"target": "sonarr", "check": checks[1], "payload": {"password": "private-secret"}}
    plan = {"revision": 1, "checks": checks, "changes": [change], "notices": ["private address"]}
    saved = setup_readiness.remember_wiring(store, plan, now=NOW)
    assert [row["state"] for row in saved["checks"]] == ["reviewed", "unavailable", "unavailable"]
    saved = setup_readiness.remember_wiring(store, plan, [{"target": "sonarr", "state": "failed"}], now=NOW)
    assert saved["checks"][1]["state"] == "unavailable"
    saved = setup_readiness.remember_wiring(store, plan, [{"target": "sonarr", "state": "created"}], now=NOW)
    assert saved["checks"][1]["state"] == "reviewed"
    assert "private" not in json.dumps(saved)


async def test_wiring_schema_failure_never_counts_as_reviewed_existing_configuration(tmp_path):
    store = Store(tmp_path)
    config = configured(["sonarr", "qbittorrent"])
    store.save(config, 1, {"sonarr": {"api_key": "synthetic-key"},
                           "qbittorrent": {"username": "synthetic", "password": "synthetic-password"}})

    def respond(request):
        assert request.method == "GET"
        if request.url.path.endswith("/schema"):
            return httpx.Response(403)
        raise AssertionError("An unauthorized schema must not be treated as an existing connection")

    plan = await build_plan(store, httpx.MockTransport(respond))
    assert plan["changes"] == []
    assert public_plan(plan)["checks"] == [{"source": "qbittorrent", "target": "sonarr", "state": "unavailable"}]
    assert setup_readiness.remember_wiring(store, plan)["checks"][0]["state"] == "unavailable"


async def test_existing_connections_have_safe_structured_review_for_every_required_pair(tmp_path):
    store = Store(tmp_path)
    config = configured(REQUEST_APPS)
    store.save(config, 1, {**{key: {"api_key": "synthetic-key"} for key in REQUEST_APPS},
                           "qbittorrent": {"username": "synthetic", "password": "synthetic-password"}})

    def respond(request):
        assert request.method == "GET"
        path = request.url.path
        if request.url.host == "plex.example":
            if path == '/identity':
                return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'fixture-server', 'claimed': True}})
            return httpx.Response(200, json={'MediaContainer': {'size': 2, 'Directory': [
                {'key': '1', 'type': 'movie', 'Location': [{'path': '/data/media/movies'}]},
                {'key': '2', 'type': 'show', 'Location': [{'path': '/data/media/tv'}]}]}})
        if request.url.host == "seerr.example":
            if path.endswith('/plex'):
                return httpx.Response(200, json={'machineId': 'fixture-server',
                    'libraries': [{'id': '1', 'enabled': True}, {'id': '2', 'enabled': True}]})
            if path.endswith('/jobs'):
                return httpx.Response(200, json=[{'id': 'plex-recently-added-scan', 'cronSchedule': '* * * * *'}])
            return httpx.Response(200, json={"version": "3.5.0"} if path.endswith("/status") else [{"id": 1}])
        if path.endswith("/schema"):
            fields = [{"name": name} for name in ("host", "port", "username", "password", "category", "baseUrl", "apiKey")]
            return httpx.Response(200, json=[{"implementation": name, "fields": fields}
                                              for name in ("QBittorrent", "Sonarr", "Radarr")])
        if path.endswith('/rootfolder'):
            return httpx.Response(200, json=[{'path': '/data/media/' + ('tv' if request.url.host == 'sonarr.example' else 'movies')}])
        implementations = ["Sonarr", "Radarr"] if request.url.host == "prowlarr.example" else ["QBittorrent", "PlexServer"]
        return httpx.Response(200, json=[{"implementation": name} for name in implementations])

    plan = await build_plan(store, httpx.MockTransport(respond))
    assert plan["changes"] == []
    assert len(plan["checks"]) == 9
    assert all(row["state"] == "preserved" for row in plan["checks"])
    reviewed = setup_readiness.remember_wiring(store, plan, now=NOW)
    assert all(row["state"] == "reviewed" for row in reviewed["checks"])
    assert "synthetic" not in json.dumps(public_plan(plan))


def test_all_inputs_are_immutable_and_output_never_exposes_paths_addresses_or_raw_errors():
    snapshot = draft(REQUEST_APPS)
    deployment = installed(REQUEST_APPS)
    deployment["operations"][0]["message"] = "private upstream password"
    collection = collected(REQUEST_APPS, error="private raw error", url="http://private.example")
    original = copy.deepcopy((snapshot, deployment, collection))
    result = setup_readiness.build(snapshot, configured(REQUEST_APPS), secret_names=REQUEST_APPS,
                                   deployment=deployment, collector=collection, now=NOW)
    assert (snapshot, deployment, collection) == original
    rendered = json.dumps(result)
    assert "/media/library" not in rendered
    assert "private" not in rendered.replace("private connection", "")
    assert "http://" not in rendered


def test_saved_observations_survive_restart_but_collector_success_is_not_invented(tmp_path):
    store = Store(tmp_path)
    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft.model_validate(
        {"apps": REQUEST_APPS, "step": 2, "data_root": "/media/library"})))
    store.save(configured(REQUEST_APPS), 1, {key: {"api_key": "synthetic-secret"} for key in REQUEST_APPS})
    setup_readiness.remember_sources(store, {"sources": [{"name": "private provider", "enabled": True,
                                                         "api_key": "private-secret"}],
                                             "apps": [{"app": "sonarr", "shared_sources": 1},
                                                      {"app": "radarr", "shared_sources": 1}]}, now=NOW)
    setup_readiness.remember_runtime(store, {"state": "ready", "checks": ["private runtime path"]}, now=NOW)
    with store.db() as db:
        saved = " ".join(row[0] for row in db.execute("SELECT data FROM setup_observations"))
    assert "private" not in saved
    reopened = Store(tmp_path)
    result = setup_readiness.read(reopened, now=NOW)
    assert checkpoint(result, "sources")["state"] == "done"
    assert checkpoint(result, "computer")["state"] == "done"
    assert checkpoint(result, "connection-plex")["state"] == "unknown"
    before = reopened.audit_rows()
    setup_readiness.read(reopened, now=NOW)
    assert reopened.audit_rows() == before
    setup_readiness.remember_sources(reopened, None, now=NOW + 1)
    assert checkpoint(setup_readiness.read(reopened, now=NOW + 1), "sources")["state"] == "needs-action"


def test_saved_settings_change_invalidates_source_evidence(tmp_path):
    store = Store(tmp_path)
    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft.model_validate(
        {"apps": REQUEST_APPS, "step": 2, "data_root": "/media/library"})))
    setup_readiness.remember_sources(store, {"sources": [{"enabled": True}],
                                            "apps": [{"app": "sonarr", "shared_sources": 1},
                                                     {"app": "radarr", "shared_sources": 1}]}, now=NOW)
    store.save(store.config()[1], 1)
    assert checkpoint(setup_readiness.read(store, now=NOW), "sources")["state"] == "unknown"


@pytest.mark.parametrize("outcome,successful,matching", [
    ({"state": "results", "authentication": "passed", "categories": "supported", "search": "results"}, 1, 1),
    ({"state": "no-matches", "authentication": "passed", "categories": "supported", "search": "no-matches"}, 1, 0),
    ({"state": "no-matches", "authentication": "passed", "categories": "supported", "search": "unknown"}, 0, 0),
    ({"state": "results", "authentication": "unknown", "categories": "supported", "search": "results"}, 0, 0),
    ({"state": "results", "authentication": "passed", "categories": "missing", "search": "results"}, 0, 0),
    ({"state": "search-failed", "authentication": "passed", "categories": "supported", "search": "failed"}, 0, 0),
])
def test_source_probe_only_advances_from_verified_auth_category_and_search(tmp_path, outcome, successful, matching):
    store = Store(tmp_path)
    setup_readiness.remember_sources(store, {"sources": [{"id": 7, "enabled": True}], "apps": []}, now=NOW)
    result = {"query": "private title", "sources": [{**outcome, "name": "private provider",
              "downloadUrl": "http://private.invalid/?apikey=secret", "apiKey": "private key"}]}
    saved = setup_readiness.remember_source_validation(store, result, media_type="movie", now=NOW)
    assert saved["successful"] == successful
    assert saved["matching"] == matching
    assert saved["source_snapshot"]["source_ids"] == [7]
    with store.db() as db:
        persisted = " ".join(row[0] for row in db.execute("SELECT data FROM setup_observations"))
    assert not any(value in persisted for value in ("private", "secret", "apikey", "query", "downloadUrl"))


def test_source_search_evidence_is_per_media_type_reopens_and_expires(tmp_path):
    store = Store(tmp_path)
    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft.model_validate(
        {"apps": ["prowlarr", "radarr", "sonarr"], "step": 2, "data_root": "/media/library"})))
    setup_readiness.remember_sources(store, {"sources": [{"id": 7, "enabled": True}], "apps": [
        {"app": key, "shared_sources": 1} for key in ("radarr", "sonarr")]}, now=NOW)
    probe = {"sources": [{"state": "no-matches", "authentication": "passed", "categories": "supported",
                          "search": "no-matches"}]}
    setup_readiness.remember_source_validation(store, probe, media_type="movie", now=NOW)
    reopened = Store(tmp_path)
    result = setup_readiness.read(reopened, now=NOW)
    assert checkpoint(result, "source-search-movie")["state"] == "done"
    assert "no matching copy" in checkpoint(result, "source-search-movie")["detail"]
    assert checkpoint(result, "source-search-tv")["state"] == "unknown"
    assert not result["ready_to_watch"] and not result["ready_to_request"]
    result = setup_readiness.read(reopened, now=NOW + 10000)
    assert checkpoint(result, "source-search-movie")["state"] == "stale"
    setup_readiness.remember_source_validation(reopened, None, media_type="movie", now=NOW)
    assert checkpoint(setup_readiness.read(reopened, now=NOW), "source-search-movie")["state"] == "needs-action"


def test_changed_source_identity_or_config_invalidates_probe_and_new_source_clears_both(tmp_path):
    store = Store(tmp_path)
    onboarding.initialize(store)
    onboarding.save(store, onboarding.SaveDraft(revision=1, draft=onboarding.SetupDraft.model_validate(
        {"apps": ["prowlarr", "radarr", "sonarr"], "step": 2, "data_root": "/media/library"})))
    source = {"sources": [{"id": 7, "enabled": True}], "apps": []}
    setup_readiness.remember_sources(store, source, now=NOW)
    probe = {"sources": [{"state": "results", "authentication": "passed", "categories": "supported", "search": "results"}]}
    for key in ("movie", "tv"):
        setup_readiness.remember_source_validation(store, probe, media_type=key, now=NOW)
    source["sources"][0]["id"] = 8
    setup_readiness.remember_sources(store, source, now=NOW)
    assert checkpoint(setup_readiness.read(store, now=NOW), "source-search-movie")["state"] == "unknown"
    source["sources"][0]["id"] = 7
    setup_readiness.remember_sources(store, source, now=NOW)
    assert checkpoint(setup_readiness.read(store, now=NOW), "source-search-movie")["state"] == "done"
    store.save(store.config()[1], store.config()[0])
    assert checkpoint(setup_readiness.read(store, now=NOW), "source-search-movie")["state"] == "unknown"
    setup_readiness.forget_source_validation(store)
    with store.db() as db:
        assert [row[0] for row in db.execute("SELECT kind FROM setup_observations")] == ["sources"]
