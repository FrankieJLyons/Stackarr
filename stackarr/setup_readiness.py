"""Read-only setup journey derived from saved choices and bounded observations.

Installed apps, authenticated APIs, source sharing and actual playback are separate
facts. This module never probes an app, runs an installer or infers playback from
an API's health. Optional observation writers retain only redacted status counts.
"""

import json
import math
import time

from . import onboarding
from .config import CATALOG
from .storage import MEDIA_APPS, layout

COMPANIONS = {"tautulli", "kuma", "cleanuparr"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _freshness(checked, now, limit):
    if not _number(checked) or checked > now + 5:
        return "unknown"
    return "fresh" if now - checked <= limit else "stale"


def _action(identity, label, target, **extra):
    return {"id": identity, "label": label, "target": target, **extra}


def _checkpoint(identity, title, state, detail, apps, action=None, *, kind="saved-choice",
                freshness="saved", checked_at=None):
    return {"id": identity, "title": title, "state": state, "detail": detail,
            "apps": list(apps), "action": action,
            "evidence": {"kind": kind, "freshness": freshness, "checked_at": checked_at}}


def build(draft_snapshot, config, *, config_revision=None, secret_names=(), deployment=None,
          collector=None, source_status=None, runtime=None, wiring_status=None, validation_status=None, now=None):
    """Calculate a journey from snapshots without changing any inputs or state."""
    now = time.time() if now is None else now
    draft = onboarding.SetupDraft.model_validate(draft_snapshot["draft"])
    selected = draft.apps
    deployment = deployment or {}
    limit = config.dashboard.stale_seconds
    secrets = set(secret_names)
    observations = {row["id"]: row for row in (collector or {}).get("integrations", [])}
    operations = sorted(deployment.get("operations", []), key=lambda row: row.get("updated", 0), reverse=True)
    # An earlier superseded attempt cannot block or complete the current journey.
    by_app = {}
    for operation in operations:
        if operation.get("state") == "superseded":
            continue
        for key in operation.get("apps", []):
            by_app.setdefault(key, operation)
    rows = []
    reconnect = _action("reconnect-installation", "Reconnect the installation computer", "setup-reconnect")
    missing_addresses = [key for key in selected if draft.choice(key).mode == "connect"
                         and not draft.choice(key).url and not config.integrations[key].url]
    choices_done = bool(selected) and (draft.step > 0 or draft_snapshot["revision"] > 1) and not missing_addresses
    rows.append(_checkpoint("choices", "Choose your experience", "done" if choices_done else "needs-action",
                            f"{len(selected)} apps selected. You can change these choices."
                            if selected and not missing_addresses else "Choose your apps and any existing app addresses.",
                            selected, None if choices_done else _action("choose-apps", "Choose apps", "setup-apps")))

    installs = [key for key in selected if draft.choice(key).mode == "install"]
    uninstalled = [key for key in installs if by_app.get(key, {}).get("state") != "needs-setup"]
    if installs:
        recorded = all(key in by_app for key in installs)
        # Navigation and port suggestions increment the draft revision. They do
        # not change which installation computer/engine this check covered.
        runtime_bound = runtime and runtime.get("install_apps") == sorted(installs)
        freshness = _freshness(runtime.get("checked_at"), now, limit) if runtime_bound else "unknown"
        if recorded:
            state, detail, freshness = "done", "Host checks passed when the saved installation was approved. Current Docker availability is a separate check.", "saved"
        elif freshness == "fresh" and runtime.get("state") == "ready":
            state, detail = "done", "Docker was checked on the installation computer. Installation checks run again before installing."
        elif freshness == "fresh" and runtime.get("state") == "needs-attention":
            state, detail = "needs-action", "Docker needs attention on the installation computer. Check its current status for the next step."
        else:
            state = "stale" if freshness == "stale" else "unknown"
            detail = "Check Docker on the installation computer before installing new apps."
        rows.append(_checkpoint("computer", "Check this computer", state, detail, installs,
                                None if state == "done" else (_action("check-runtime", "Check Docker", "setup-check-runtime")
                                                             if deployment.get("available") else reconnect),
                                kind="installation-preflight" if recorded else "runtime-check", freshness=freshness,
                                checked_at=runtime.get("checked_at") if runtime_bound else None))
        media = [key for key in installs if key in MEDIA_APPS]
        if media:
            valid = layout(draft.data_root, installs)["valid"]
            rows.append(_checkpoint("storage", "Choose your media folder", "done" if valid else "needs-action",
                                    "Folder address saved. Access, free space and imports still need verification."
                                    if valid else "Choose a dedicated media folder on the installation computer.", media,
                                    None if valid else _action("choose-storage", "Choose media folder", "setup-storage")))
        pending = next((by_app[key] for key in installs if key in by_app
                        and by_app[key].get("state") != "needs-setup"), None)
        cached = bool(deployment.get("status_stale"))
        if cached and any(key in by_app for key in installs):
            state, detail = "stale", "Installation progress is the last known status. Reconnect to the installation computer and check again."
            action = _action("check-progress", "Check installation progress", "setup-install-refresh")
        elif pending:
            status = pending.get("state")
            if status in {"queued", "running"}:
                state, detail = "in-progress", "Your saved installation is in progress. Completed work is retained."
                action = _action("check-progress", "Check installation progress", "setup-install-refresh")
            elif status in {"failed", "interrupted"}:
                state, detail = "needs-action", "Installation needs attention. Review the saved progress and resume; existing app data is retained."
                action = _action("resume-install", "Review and resume installation", "installation-progress", installation=pending["id"])
            elif status == "ports-blocked":
                state, detail = "needs-action", "Some selected ports are unavailable. Review the saved installation to choose free ports."
                action = _action("check-progress", "Review installation ports", "setup-install-refresh")
            else:
                state, detail = "unknown", "The saved installation needs a current status check."
                action = _action("check-progress", "Check installation progress", "setup-install-refresh")
        elif uninstalled:
            conflicts = [key for key in uninstalled if config.integrations[key].enabled or config.integrations[key].url or key in secrets]
            state, detail = "needs-action", "Review the selected new apps before downloading or installing them."
            action = _action("review-install", "Review installation", "setup-install-review")
            if conflicts:
                detail = "A selected new app already has saved settings. Review its choice or connection settings before installing."
                action = _action("choose-apps", "Review selected apps", "setup-apps")
        else:
            state, detail, action = "done", "The saved installation completed. Account setup, app connections and playback are separate checks.", None
        if state != "done" and not deployment.get("available"):
            action = reconnect
        rows.append(_checkpoint("installation", "Install your selected apps", state, detail, installs, action,
                                kind="installation-receipt", freshness="stale" if cached else "saved" if by_app else "unknown",
                                checked_at=deployment.get("last_checked")))

    # Each selected app gets exactly one connection task. Unselected apps never
    # appear, even if the installation receipt or dashboard contains other apps.
    connection_order = (["plex"] if "plex" in selected else []) + [key for key in selected if key != "plex"]
    for key in connection_order:
        app = config.integrations[key]
        observation = observations.get(key, {})
        checked = (observation.get("collected_at") if observation.get("state") == "ready"
                   else observation.get("attempted_at"))
        freshness = _freshness(checked, now, limit)
        action = _action("test-connections", "Test saved connections", "test", app=key)
        operation = by_app.get(key)
        if not app.enabled or not app.url or key not in secrets:
            state, detail, freshness = "needs-action", "Save this app's address and private connection details, then test the connection.", "saved"
            action = _action("accounts", "Open connection settings", "setup-settings", app=key)
            if operation and operation.get("state") == "needs-setup":
                if key in COMPANIONS:
                    detail = "Review the companion setup to prepare this installed app's private connection."
                    action = _action("companion-review", "Review companion setup", "companion-setup-review", app=key, installation=operation["id"])
                else:
                    detail = ("Finish account setup in this app, then return and choose Finish connecting."
                              if key in {"plex", "seerr"} else "Finish connecting the installed app to save its private connection details.")
                    action = _action("finish-connecting", "Connect Plex for watching" if key == "plex" else "Connect requests" if key == "seerr" else "Finish connecting", "finish-connecting", app=key, installation=operation["id"])
        elif observation.get("state") == "ready" and observation.get("stale") is False and freshness == "fresh":
            state, detail, action = "done", "The saved authenticated API connection responded. This does not verify playback or media imports.", None
        elif observation.get("state") == "unavailable" and freshness == "fresh":
            state, detail = "needs-action", "The last connection test failed. Review this app's availability and credentials, then try again."
        elif freshness == "stale" or observation.get("state") == "ready" and observation.get("stale"):
            state, detail, freshness = "stale", "The previous connection result is out of date. Test the saved connection again.", "stale"
        else:
            state, detail, freshness = "unknown", "Connection details are saved. Test them to check authentication and availability.", "unknown"
        rows.append(_checkpoint("connection-" + key, "Connect " + CATALOG[key]["name"], state, detail, [key], action,
                                kind="authenticated-api", freshness=freshness, checked_at=checked))

    targets = [key for key in ("sonarr", "radarr") if key in selected]
    required_links = {(source, target) for target in targets for source in ("qbittorrent", "prowlarr")
                      if source in selected}
    if "seerr" in selected:
        required_links.update((target, "seerr") for target in targets)
    if "plex" in selected and targets:
        required_links.update(("plex", target) for target in targets)
        if "seerr" in selected:
            required_links.add(("plex", "seerr"))
    reviewed_links = set()
    wiring_bound = wiring_status and wiring_status.get("config_revision") == config_revision
    if wiring_bound:
        reviewed_links = {(row["source"], row["target"]) for row in wiring_status.get("checks", [])
                          if row.get("state") == "reviewed"}
    links_reviewed = bool(required_links) and required_links <= reviewed_links
    if "prowlarr" in selected and targets:
        bound = source_status and source_status.get("config_revision") == config_revision
        freshness = _freshness(source_status.get("checked_at"), now, limit) if bound else "unknown"
        state, detail = "unknown", "Check that your chosen sources are enabled and shared with the selected TV and movie apps."
        if freshness == "stale":
            state, detail = "stale", "Source sharing was checked earlier. Check it again for current configuration."
        elif freshness == "fresh":
            shared = source_status.get("shared_sources", {})
            if source_status.get("state") == "unavailable":
                state, detail = "needs-action", "Source status could not be checked. Check Prowlarr and its saved connection, then retry."
            elif source_status.get("enabled_sources", 0) > 0 and all(shared.get(key, 0) > 0 for key in targets):
                state, detail = "done", "Enabled sources and sharing were observed. Authentication, categories and usable search results still need verification."
            else:
                state, detail = "needs-action", "Add an enabled source and check sharing with each selected TV or movie app."
        rows.append(_checkpoint("sources", "Choose and share your sources", state, detail, ["prowlarr", *targets],
                                None if state == "done" else _action("source-setup", "Choose content sources", "indexer-setup")
                                if not bound or not source_status.get("enabled_sources", 0)
                                else _action("source-check", "Check source sharing", "indexers-check"),
                                kind="source-configuration", freshness=freshness,
                                checked_at=source_status.get("checked_at") if bound else None))
        if (state == "needs-action" and bound and freshness == "fresh"
                and source_status.get("enabled_sources", 0) > 0 and not links_reviewed):
            rows[-1]["detail"] = "Sources are enabled, but a selected TV or movie app has no shared source. Review the app connections, then check source sharing again."
            rows[-1]["action"] = _action("wiring-preview", "Review source sharing connections", "wiring-preview")
        elif state == "needs-action" and bound and source_status.get("enabled_sources", 0) > 0:
            rows[-1]["detail"] = "Sources are enabled, but a selected TV or movie app has no shared source. Existing app settings were preserved; review source sharing in Prowlarr, then check again."
    if required_links:
        rows.append(_checkpoint("connections", "Review app connections", "done" if links_reviewed else "unknown",
                                "App configuration was reviewed. Existing settings were preserved; requests, imports and playback still need functional verification."
                                if links_reviewed else "Review the connections between your selected apps. Saved API connections alone cannot prove requests or imports work.",
                                [key for key in selected if key in {*targets, "qbittorrent", "prowlarr", "seerr", "plex"}],
                                None if links_reviewed else _action("wiring-preview", "Review app connections", "wiring-preview"),
                                kind="configuration-review", freshness="saved" if links_reviewed else "unknown",
                                checked_at=wiring_status.get("checked_at") if wiring_bound else None))
    if "prowlarr" in selected and targets:
        for media_type, app in (("movie", "radarr"), ("tv", "sonarr")):
            if app not in targets:
                continue
            observation = (validation_status or {}).get(media_type) or {}
            bound = (observation.get("config_revision") == config_revision
                     and observation.get("source_snapshot") == source_signature(source_status))
            freshness = _freshness(observation.get("checked_at"), now, limit) if bound else "unknown"
            state, detail = "unknown", "Test a title to check provider sign-in, the selected category and a real search response. This does not download media."
            if freshness == "stale":
                state, detail = "stale", "The previous source-search test is out of date. Test another title for a current result."
            elif freshness == "fresh" and observation.get("successful", 0):
                state = "done"
                detail = ("A source answered the test search with results. Release suitability, downloads, imports and playback still need verification."
                          if observation.get("matching", 0) else "A source answered the test search but found no matching copy. Try another title; this does not indicate a broken connection.")
                if observation.get("failed", 0) or observation.get("unverified", 0):
                    detail += " Other sources still need attention; open the test details."
            elif freshness == "fresh":
                state, detail = "needs-action", "The source search could not be verified. Open the test details to distinguish account, category and search problems."
            rows.append(_checkpoint("source-search-" + media_type,
                                    "Test movie sources" if media_type == "movie" else "Test TV sources", state, detail,
                                    ["prowlarr", app], None if state == "done" else _action(
                                        "source-validation", "Test a movie search" if media_type == "movie" else "Test a TV search",
                                        "indexer-validation-query", media_type=media_type), kind="source-search",
                                    freshness=freshness, checked_at=observation.get("checked_at") if bound else None))
    if "plex" in selected or targets or "seerr" in selected:
        verification_title = "Verify your first watch" if "plex" in selected else "Verify requests and imports" if targets else "Verify requests"
        rows.append(_checkpoint("verification", verification_title, "unknown",
                                "Playback has not been verified. Test a permitted movie and episode through your chosen workflow and on your intended device."
                                if "plex" in selected else "Request, search, download and import have not been verified together. Test your chosen workflow with permitted media."
                                if targets else "Requests have not been verified. Test an authorized request in Seerr using its existing media-server and library configuration.",
                                [key for key in selected if key not in COMPANIONS],
                                _action("verification", "See what still needs verification", "setup-verification"),
                                kind="functional-verification", freshness="unknown"))
    next_row = next((row for row in rows if row["state"] != "done" and row["action"]), None)
    return {"version": 1, "draft_revision": draft_snapshot["revision"], "config_revision": config_revision,
            "generated_at": now, "selected_apps": list(selected), "checkpoints": rows,
            "next_action": {**next_row["action"], "checkpoint_id": next_row["id"]} if next_row else None,
            "summary": {"done": sum(row["state"] == "done" for row in rows), "total": len(rows)},
            "ready_to_watch": False, "ready_to_request": False}


def _remember(store, kind, observation):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS setup_observations (kind TEXT PRIMARY KEY, data TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO setup_observations VALUES(?,?)", (kind, json.dumps(observation)))
    return observation


def remember_sources(store, result, *, config_revision=None, now=None):
    """Save counts only after an explicit source check; None records a failed check."""
    revision = store.config()[0] if config_revision is None else config_revision
    shared = {}
    for row in (result or {}).get("apps", []):
        count = row.get("shared_sources")
        if row.get("app") in {"sonarr", "radarr"} and type(count) is int and count >= 0:
            shared[row["app"]] = count
    observation = {"config_revision": revision, "checked_at": time.time() if now is None else now,
                   "state": "observed" if result is not None else "unavailable",
                   "enabled_sources": sum(row.get("enabled") is True for row in (result or {}).get("sources", [])),
                   "shared_sources": shared,
                   "source_ids": sorted({row["id"] for row in (result or {}).get("sources", [])
                                         if type(row.get("id")) is int and row.get("enabled") is True})}
    return _remember(store, "sources", observation)


def source_signature(observation):
    """Bind a check to saved nonsecret source identities and sharing counts."""
    observation = observation or {}
    return {"enabled_sources": observation.get("enabled_sources", 0),
            "shared_sources": observation.get("shared_sources", {}),
            "source_ids": observation.get("source_ids", [])}


def remember_source_validation(store, result, *, media_type, config_revision=None, now=None):
    """Store probe outcomes only; provider details, queries and releases stay private."""
    if media_type not in {"movie", "tv"}:
        raise ValueError("Choose movie or TV source testing.")
    revision = store.config()[0] if config_revision is None else config_revision
    with store.db() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        row = db.execute("SELECT data FROM setup_observations WHERE kind='sources'").fetchone() if "setup_observations" in tables else None
    sources = json.loads(row[0]) if row else {}
    outcomes = (result or {}).get("sources", [])
    verified = [outcome for outcome in outcomes if outcome.get("authentication") == "passed"
                and outcome.get("categories") == "supported"
                and outcome.get("state") in {"results", "no-matches"}
                and outcome.get("search") == outcome.get("state")]
    observation = {"config_revision": revision, "media_type": media_type,
                   "checked_at": time.time() if now is None else now,
                   "source_snapshot": source_signature(sources), "successful": len(verified),
                   "matching": sum(outcome["state"] == "results" for outcome in verified),
                   "failed": sum(outcome.get("state") in {"authentication-failed", "test-failed", "search-failed", "category-missing"} for outcome in outcomes),
                   "unverified": sum(outcome.get("state") in {"unverified", "not-tested"} for outcome in outcomes),
                   "available": result is not None}
    return _remember(store, "source-validation-" + media_type, observation)


def forget_source_validation(store):
    """A newly saved source requires fresh probes without clearing its settings."""
    with store.db() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='setup_observations'").fetchone()
        if exists:
            db.execute("DELETE FROM setup_observations WHERE kind IN ('source-validation-movie','source-validation-tv')")


def remember_runtime(store, result, *, draft_revision=None, now=None):
    """Retain only the runtime state, bound to the choices checked by the caller."""
    snapshot = onboarding.read(store)
    revision = snapshot["revision"] if draft_revision is None else draft_revision
    draft = onboarding.SetupDraft.model_validate(snapshot["draft"])
    state = result.get("state")
    observation = {"draft_revision": revision, "install_apps": sorted(draft.install_apps()),
                   "checked_at": time.time() if now is None else now,
                   "state": state if state in {"ready", "needs-attention", "not-checked"} else "not-checked"}
    return _remember(store, "runtime", observation)


def remember_wiring(store, plan, results=None, *, now=None):
    """Retain explicit configuration reviews, never functional-link readiness.

    A skipped or failed schema/authentication check stays unavailable. Previewed
    proposals require a corresponding successful apply result before completion.
    Preserving an existing entry records that review only, not its correctness.
    """
    successful = set()
    if results is not None:
        for change, result in zip(plan.get("changes", []), results, strict=False):
            check = change.get("check", {})
            if (result.get("target") == change.get("target")
                    and result.get("state") in {"created", "preserved existing"}):
                successful.add((check.get("source"), check.get("target")))
    checks = []
    for row in plan.get("checks", []):
        source, target = row.get("source"), row.get("target")
        if source not in CATALOG or target not in CATALOG:
            continue
        reviewed = row.get("state") == "preserved" or (
            row.get("state") == "proposed" and (source, target) in successful)
        checks.append({"source": source, "target": target, "state": "reviewed" if reviewed else "unavailable"})
    return _remember(store, "wiring", {"config_revision": plan.get("revision"),
                                      "checked_at": time.time() if now is None else now, "checks": checks})


def read(store, *, collector=None, deployment=None, source_status=None, runtime=None, wiring_status=None, validation_status=None, now=None):
    """Reconstruct progress from durable facts; no controller or upstream calls."""
    with store.db() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        observations = {}
        if "setup_observations" in tables:
            for kind, data in db.execute("SELECT kind,data FROM setup_observations"):
                try:
                    observations[kind] = json.loads(data)
                except (ValueError, TypeError):
                    pass
        if deployment is None:
            deployment = {"available": False, "operations": []}
            if "controller_status_snapshot" in tables:
                row = db.execute("SELECT checked,operations FROM controller_status_snapshot WHERE id=1").fetchone()
                if row:
                    deployment.update(operations=json.loads(row[1]), last_checked=row[0], status_stale=True)
            elif "deployments" in tables:
                deployment["operations"] = [{"id": identity, "state": state, "updated": updated,
                                              "apps": json.loads(payload).get("apps", [])}
                                             for identity, state, updated, payload in db.execute(
                                                 "SELECT id,state,updated,payload FROM deployments ORDER BY created DESC LIMIT 20")]
    revision, config = store.config()
    return build(onboarding.read(store), config, config_revision=revision, secret_names=store.secret_names(),
                 deployment=deployment, collector=collector,
                 source_status=source_status if source_status is not None else observations.get("sources"),
                 runtime=runtime if runtime is not None else observations.get("runtime"),
                 wiring_status=wiring_status if wiring_status is not None else observations.get("wiring"),
                 validation_status=validation_status if validation_status is not None else {
                     key: observations.get("source-validation-" + key) for key in ("movie", "tv")}, now=now)
