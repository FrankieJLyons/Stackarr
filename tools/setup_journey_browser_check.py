"""Exercise the saved setup journey against an isolated app and synthetic host boundaries.

This is browser/API integration evidence, not Docker, source, import or playback
certification. Every upstream request is rejected; host checks and app wiring are
synthetic. Only the explicitly chosen new output directory contains test state.
"""

import argparse
import json
import os
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from playwright.sync_api import expect, sync_playwright

from stackarr import onboarding, setup_readiness
from stackarr.config import APP_IDS, CATALOG, Config
from stackarr.pairing import PairingGate
from stackarr.server import create_app

REQUEST_APPS = {"plex", "seerr", "sonarr", "radarr", "prowlarr", "qbittorrent"}
PASSWORD = "synthetic journey browser password"


class Fixture:
    def __init__(self, app, media):
        self.app = app
        self.store = app.state.store
        self.media = media
        self.operations = []
        self.available = True
        self.blocked = []
        self.source_checks = 0
        self.search_checks = 0
        self.wiring_checks = 0

    def snapshot(self):
        result = {"available": self.available, "host_checks": self.available,
                  "controller": "connected" if self.available else "unavailable",
                  "folder_browser": True, "folder_picker": False, "actions": [],
                  "operations": self.operations, "last_checked": time.time(), "status_stale": False}
        result["journey"] = setup_readiness.read(
            self.store, collector=self.app.state.collector.view(), deployment=result)
        return result

    def save_draft(self, apps, *, step=2, choices=None, media=True):
        old = onboarding.read(self.store)
        draft = onboarding.SetupDraft(apps=list(apps), step=step,
                                      data_root=str(self.media) if media else "", choices=choices or {})
        return onboarding.save(self.store, onboarding.SaveDraft(revision=old["revision"], draft=draft))

    def configure(self, apps, *, installed=False):
        revision, old = self.store.config()
        config = Config()
        config.dashboard.refresh_seconds = 3600
        config.dashboard.stale_seconds = 7200
        credentials = {key: None for key in old.integrations}
        for key in apps:
            app = config.integrations[key]
            app.enabled = True
            app.mode = "install" if installed else "connect"
            app.url = f"http://{key}.synthetic.invalid"
            app.browser_url = app.url
            credentials[key] = {"api_key": "synthetic-private-fixture-key"}
        self.store.save(config, revision, credentials)
        self.app.state.collector.snapshots.clear()
        for key in apps:
            self.app.state.collector.snapshots[key] = {
                "connection": self.app.state.collector.connection_key(key, config.integrations[key]),
                "state": "ready", "collected_at": time.time(), "attempted_at": time.time(), "tables": {},
            }
        self.operations = [{"id": "a" * 32, "state": "needs-setup", "updated": time.time(),
                            "apps": list(apps), "message": "Synthetic installation receipt; no apps installed.",
                            "links": [{"app": key, "url": config.integrations[key].url} for key in apps]}] if installed else []
        with self.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS setup_observations (kind TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("DELETE FROM setup_observations")
        return config

    def ports(self):
        draft = onboarding.SetupDraft.model_validate(onboarding.read(self.store)["draft"])
        return [{"app": key, "name": CATALOG[key]["name"], "port": 28100 + APP_IDS.index(key),
                 "previous": draft.choice(key).port or CATALOG[key]["port"], "status": "available"}
                for key in draft.install_apps()]

    async def sources(self, *_args, **_kwargs):
        self.source_checks += 1
        return {"sources": [{"id": 7, "name": "Synthetic permitted source", "enabled": True}], "apps": [
            {"app": key, "name": CATALOG[key]["name"], "shared_sources": 1} for key in ("sonarr", "radarr")]}

    async def catalog(self, *_args, **_kwargs):
        return {"providers": [], "notice": "Synthetic empty provider catalog; no upstream API contacted."}

    async def validate_sources(self, _store, check, *_args, **_kwargs):
        self.search_checks += 1
        return {"media_type": check.media_type, "state": "no-matches", "sources": [
            {"id": 7, "name": "Synthetic permitted source", "state": "no-matches", "result_count": 0,
             "authentication": "passed", "categories": "supported", "search": "no-matches",
             "detail": "Synthetic successful search with no matches."}], "sharing": await self.sources(),
            "checked_sources": 1, "total_enabled": 1, "limited": False,
            "notice": "Synthetic source result only; no source was contacted and no media was downloaded."}

    async def wiring(self, *_args, **_kwargs):
        self.wiring_checks += 1
        checks = [{"source": source, "target": target, "state": "preserved"}
                  for source in ("qbittorrent", "prowlarr") for target in ("sonarr", "radarr")]
        checks.extend({"source": key, "target": "seerr", "state": "preserved"} for key in ("sonarr", "radarr"))
        checks.extend({"source": "plex", "target": key, "state": "preserved"}
                      for key in ("sonarr", "radarr", "seerr"))
        return {"revision": self.store.config()[0], "changes": [], "checks": checks,
                "notices": ["Synthetic existing app connections preserved. No upstream API was contacted."]}

    def routes(self):
        async def home():
            return {key: {"items": [], "checked_at": time.time()}
                    for key in ("available", "requests", "trending", "movies", "tv")}

        async def deployments():
            return self.snapshot()

        async def ports():
            return {"ports": self.ports(), "notice": "Synthetic available ports; no sockets probed."}

        async def suggestions():
            return {"suggestions": self.ports(), "notice": "Synthetic available ports."}

        async def review():
            draft = onboarding.SetupDraft.model_validate(onboarding.read(self.store)["draft"])
            return {"apps": self.ports(), "notice": "Synthetic review only; installation is blocked in this fixture.",
                    "media_folder": draft.data_root, "create_folders": [], "review_token": "fixture-review-token-00000000000000"}

        for path, endpoint, methods in [
            ("/api/home", home, ["GET"]),
            ("/api/deployments", deployments, ["GET"]),
            ("/api/onboarding/check-ports", ports, ["POST"]),
            ("/api/onboarding/suggest-ports", suggestions, ["POST"]),
            ("/api/deployments/review", review, ["POST"]),
        ]:
            self.app.router.routes.insert(0, APIRoute(path, endpoint, methods=methods))

        allowed_mutations = {"/api/setup", "/api/login", "/api/logout", "/api/launcher/pair", "/api/onboarding",
                             "/api/onboarding/check-ports", "/api/onboarding/suggest-ports",
                             "/api/onboarding/runtime-check", "/api/deployments/review", "/api/indexers/validate"}
        allowed_reads = {"/api/appearance", "/api/native-imports", "/api/overview/storage", "/api/library-mapping", "/api/session", "/api/config", "/api/status", "/api/deployments", "/api/onboarding", "/api/home",
                         "/api/onboarding/readiness", "/api/onboarding/storage", "/api/onboarding/folders",
                         "/api/onboarding/plan", "/api/indexers/status", "/api/wiring/preview", "/api/indexers/catalog"}

        @self.app.middleware("http")
        async def fixture_guard(request: Request, call_next):
            allowed = allowed_reads if request.method in {"GET", "HEAD"} else allowed_mutations
            if request.url.path.startswith("/api/") and request.url.path not in allowed:
                self.blocked.append(f"{request.method} {request.url.path}")
                return JSONResponse({"detail": "Action blocked by the isolated browser fixture"}, status_code=418)
            return await call_next(request)


def open_setup(page, origin):
    page.goto(origin)
    page.wait_for_function("() => document.querySelector('button[data-view=setup]')")
    page.locator('button[data-view="setup"]').click()
    expect(page.locator('.setup-roadmap')).to_be_visible()


def current_action(page):
    identity = page.evaluate("setupDeployment.journey.next_action.checkpoint_id")
    return page.locator('[data-setup-checkpoint="' + identity + '"]')


def next_action(page, text):
    page.wait_for_function("label => setupDeployment.journey?.next_action?.label === label", arg=text)
    # A planning workspace keeps the checklist one explicit navigation away.
    if page.locator('[data-setup-task=""]').count():
        page.locator('[data-setup-task=""]').first.click()
    expect(current_action(page)).to_have_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    media = output / "test-media"
    media.mkdir()
    sentinel = media / "preserve.txt"
    sentinel.write_text("Synthetic setup journey sentinel.", encoding="utf-8")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    pairing = PairingGate()
    errors, external_requests, upstream_requests, scenarios = [], [], [], []
    report = {"passed": False, "scenarios": scenarios, "page_errors": errors,
              "external_requests": external_requests, "upstream_requests": upstream_requests,
              "scope": "Isolated synthetic browser/API checks only; no installation, acquisition, import or playback."}
    server = None
    thread = None
    page = None

    def reject_upstream(request):
        upstream_requests.append(str(request.url))
        raise AssertionError("The setup browser fixture must never contact upstream applications")

    environment = {key: value for key, value in os.environ.items()
                   if key not in {"STACKARR_CONTROLLER_SHARED", "STACKARR_UPDATE_CHECKING", "STACKARR_MEDIA_ROOTS"}}
    try:
        with patch.dict(os.environ, environment, clear=True):
            app = create_app(output / "state", origin=origin, pairing=pairing, background=False, host_checks=True,
                             transport=httpx.MockTransport(reject_upstream),
                             media_roots=[{"path": str(media), "host_path": str(media), "label": "Test media"}])
            fixture = Fixture(app, media)
            fixture.routes()
            runtime = {"state": "ready", "checks": [{"detail": "Synthetic Docker check passed."}],
                       "notice": "Fixture result only; Docker was not contacted."}
            with patch("stackarr.docker_runtime.inspect", return_value=runtime), \
                    patch("stackarr.indexers.status", fixture.sources), patch("stackarr.indexers.catalog", fixture.catalog), \
                    patch("stackarr.indexers.validate", fixture.validate_sources), patch("stackarr.wiring.build_plan", fixture.wiring):
                server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
                thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
                thread.start()
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(.05)
                assert server.started, "Isolated test server did not start"
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})

                    def local_only(route):
                        if urlsplit(route.request.url).netloc == urlsplit(origin).netloc:
                            route.continue_()
                        else:
                            external_requests.append(route.request.url)
                            route.abort()

                    context.route("**/*", local_only)
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(origin)
                    page.get_by_role("button", name="Request setup approval").click()
                    page.get_by_text("Your code:", exact=False).wait_for()
                    assert pairing.approve(pairing.display_code())
                    page.get_by_label("Create a password", exact=True).fill(PASSWORD)
                    page.get_by_role("button", name="Continue to setup").click()
                    page.get_by_role("button", name="Review app choices", exact=True).click()
                    page.get_by_role("button", name="Movies & TV · recommended", exact=True).click()
                    assert set(page.locator('[id^="setup-"][type="checkbox"]:checked').evaluate_all(
                        "nodes => nodes.map(node => node.id.slice(6)).filter(key => key !== 'auto-ports')")) == REQUEST_APPS
                    page.get_by_role("button", name="Save & continue").click()
                    expect(page.locator("#setup-selected-folder")).to_have_text(media.name)
                    assert set(onboarding.read(fixture.store)["draft"]["apps"]) == REQUEST_APPS
                    expect(page.locator("#setup-selected-folder-path")).to_have_text(str(media))
                    expect(page.locator("#setup-selected-folder-path")).to_be_hidden()
                    page.get_by_text("See folder location", exact=True).click()
                    expect(page.locator("#setup-selected-folder-path")).to_be_visible()
                    page.get_by_text("See folder location", exact=True).click()
                    expect(page.get_by_label("Movies request quality", exact=True)).to_have_value("HD-1080p")
                    expect(page.get_by_label("TV request quality", exact=True)).to_have_value("HD-1080p")
                    for name, subpath in [("Movies", "movies"), ("TV", "tv")]:
                        location = page.get_by_text(str(media / "media" / subpath), exact=True)
                        expect(location).to_be_hidden()
                        page.get_by_text(f"See {name} folder location", exact=True).click()
                        expect(location).to_be_visible()
                        page.get_by_text(f"See {name} folder location", exact=True).click()
                    page.get_by_label("Movies request quality", exact=True).select_option("Ultra-HD")
                    page.get_by_label("TV request quality", exact=True).select_option("other")
                    page.get_by_label("TV other quality", exact=True).select_option("SD")
                    page.get_by_role("button", name="Save & continue").click()
                    expect(page.get_by_text("Request quality: Movies · 4K / UHD · TV · SD", exact=True)).to_be_visible()
                    next_action(page, "Check Docker")
                    saved = onboarding.read(fixture.store)
                    assert saved["draft"]["choices"]["radarr"]["quality_profile"] == "Ultra-HD"
                    assert saved["draft"]["choices"]["sonarr"]["quality_profile"] == "SD"
                    open_setup(page, origin)
                    assert onboarding.read(fixture.store) == saved
                    next_action(page, "Check Docker")
                    current_action(page).click()
                    expect(page.locator("#setup-apps")).to_be_visible()
                    next_action(page, "Review installation")
                    assert onboarding.read(fixture.store)["draft"]["step"] == 0
                    current_action(page).click()
                    expect(page.get_by_role("button", name="Download & install these apps", exact=True)).to_be_visible()
                    assert onboarding.read(fixture.store)["draft"]["step"] == 2
                    assert not any(app.enabled for app in fixture.store.config()[1].integrations.values())
                    scenarios.append("Six-app preset, exact paths in collapsed details, independent quality, resume and Docker-to-review next actions")
                    page.get_by_role("button", name="Back", exact=True).click()
                    expect(page.get_by_label("Movies request quality", exact=True)).to_have_value("Ultra-HD")
                    expect(page.get_by_label("TV other quality", exact=True)).to_have_value("SD")
                    page.screenshot(path=str(output / "journey-storage-desktop.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(output / "journey-storage-phone.png"), full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})

                    fixture.configure([])
                    fixture.save_draft([], step=0, media=False)
                    open_setup(page, origin)
                    page.get_by_role("button", name="Review app choices", exact=True).click()
                    page.get_by_role("button", name="Monitoring only", exact=True).click()
                    page.get_by_role("button", name="Save & continue").click()
                    expect(page.get_by_role("heading", name="No media folder needed", exact=True)).to_be_visible()
                    assert onboarding.read(fixture.store)["draft"]["apps"] == ["kuma"]
                    fixture.configure(["kuma"], installed=True)
                    fixture.save_draft(["kuma"], media=False)
                    open_setup(page, origin)
                    journey = fixture.snapshot()["journey"]
                    assert not any(row["id"] in {"storage", "sources", "connections", "verification"} for row in journey["checkpoints"])
                    assert journey["next_action"] is None
                    assert page.locator("#setup-verification").count() == 0
                    scenarios.append("Kuma-only preset and installed journey omit media, sources, requests and playback requirements")

                    fixture.configure(["plex"])
                    old_config = fixture.store.config()[1].model_dump()
                    old_secret = fixture.store.secret("plex")
                    fixture.save_draft(["plex", "seerr"], step=0, media=False, choices={
                        "plex": {"mode": "connect", "url": "http://plex.synthetic.invalid"}, "seerr": {"mode": "install"}})
                    open_setup(page, origin)
                    page.get_by_role("button", name="Review app choices", exact=True).click()
                    page.get_by_role("button", name="Save & continue").click()
                    expect(page.get_by_role("heading", name="No media folder needed", exact=True)).to_be_visible()
                    page.get_by_role("button", name="Save & continue").click()
                    expect(page.get_by_role("heading", name="Your choices", exact=True)).to_be_visible()
                    assert fixture.store.config()[1].model_dump() == old_config
                    assert fixture.store.secret("plex") == old_secret
                    journey = fixture.snapshot()["journey"]
                    assert next(row for row in journey["checkpoints"] if row["id"] == "computer")["apps"] == ["seerr"]
                    assert not any(row["id"] == "storage" for row in journey["checkpoints"])
                    scenarios.append("Mixed existing Plex and new Seerr retain existing configuration and credentials")

                    fixture.configure(sorted(REQUEST_APPS), installed=True)
                    fixture.save_draft(sorted(REQUEST_APPS))
                    open_setup(page, origin)
                    next_action(page, "Choose content sources")
                    current_action(page).click()
                    expect(page.locator("#indexer-setup")).to_be_visible()
                    expect(page.get_by_text("No guided provider forms are available from this Prowlarr version.", exact=False)).to_be_visible()
                    page.locator("#indexers-check").click()
                    next_action(page, "Review app connections")
                    assert fixture.source_checks == 1
                    current_action(page).click()
                    expect(page.get_by_text("No new connection changes are ready. Check any notices below.", exact=True)).to_be_visible()
                    next_action(page, "Test a movie search")
                    assert fixture.wiring_checks == 1
                    for media_type, label in (("movie", "Test a movie search"), ("tv", "Test a TV search")):
                        next_action(page, label)
                        current_action(page).click()
                        expect(page.locator("#indexer-validation-query")).to_be_focused()
                        expect(page.locator("#indexer-validation-type")).to_have_value(media_type)
                        page.locator("#indexer-validation-query").fill("Synthetic permitted sample")
                        page.locator("#indexers-validate").click()
                        expect(page.locator("#indexer-validation-result")).to_contain_text("Sources responded, but no matching copy was found")
                    assert fixture.search_checks == 2
                    next_action(page, "See what still needs verification")
                    journey = fixture.snapshot()["journey"]
                    assert next(row for row in journey["checkpoints"] if row["id"] == "connections")["state"] == "done"
                    assert journey["ready_to_watch"] is False and journey["ready_to_request"] is False
                    current_action(page).click()
                    expect(page.locator("#setup-verification")).to_be_visible()
                    expect(page.locator(".setup-roadmap")).to_be_visible()
                    page.screenshot(path=str(output / "journey-request-checklist.png"), full_page=True)
                    saved = onboarding.read(fixture.store)
                    open_setup(page, origin)
                    assert onboarding.read(fixture.store) == saved
                    next_action(page, "See what still needs verification")
                    scenarios.append("Synthetic six-app APIs, provider selection, source sharing, preserved wiring and separate movie/TV search checks advance to explicitly unverified functional checks after reload")

                    fixture.configure(["plex", "seerr"])
                    fixture.save_draft(["plex"], step=0, media=False, choices={
                        "plex": {"mode": "connect", "url": "http://plex.synthetic.invalid"}})
                    open_setup(page, origin)
                    next_action(page, "See what still needs verification")
                    assert page.locator("#setup-verification").count() == 0
                    current_action(page).click()
                    expect(page.locator("#setup-verification")).to_be_visible()
                    assert onboarding.read(fixture.store)["draft"]["step"] == 0
                    assert page.locator('#setup-verification a[href*="seerr"]').count() == 0
                    expect(page.locator("#setup-verification")).not_to_contain_text("request")
                    expect(page.locator("#setup-verification")).not_to_contain_text("imported")
                    assert page.locator("#setup-reconnect").count() == 0
                    scenarios.append("Plex-only saved step zero navigates to verification, excludes enabled unselected Seerr and needs no acquisition/import")

                    fixture.configure(["plex", "seerr"])
                    fixture.save_draft(["seerr"], step=0, media=False, choices={
                        "seerr": {"mode": "connect", "url": "http://seerr.synthetic.invalid"}})
                    open_setup(page, origin)
                    next_action(page, "See what still needs verification")
                    current_action(page).click()
                    expect(page.locator("#setup-verification")).to_be_visible()
                    expect(page.locator('#setup-verification button[data-view="home"]')).to_be_visible()
                    expect(page.locator('#setup-verification button[data-view="requests"]')).to_be_visible()
                    assert page.locator('#setup-verification a[href*="plex"]').count() == 0
                    assert fixture.snapshot()["journey"]["ready_to_request"] is False
                    assert page.locator("#setup-reconnect").count() == 0
                    scenarios.append("Seerr-only retains request verification and excludes unselected Plex playback")

                    fixture.available = False
                    fixture.configure([])
                    fixture.save_draft(["plex"], step=1)
                    open_setup(page, origin)
                    next_action(page, "Reconnect the installation computer")
                    current_action(page).click()
                    expect(page.locator("#setup-reconnect")).to_be_visible()
                    page.get_by_role("button", name="Check installation connection", exact=True).click()
                    expect(page.locator("#setup-reconnect")).to_be_visible()
                    next_action(page, "Reconnect the installation computer")
                    assert page.locator("#setup-install-review").count() == 0
                    scenarios.append("Unavailable installation routes to an explicit reconnection check without offering an absent install control")

                    assert not fixture.blocked, fixture.blocked
                    assert not upstream_requests, upstream_requests
                    assert not external_requests, external_requests
                    assert not errors, errors
                    assert sentinel.read_text(encoding="utf-8") == "Synthetic setup journey sentinel."
                    assert list(media.iterdir()) == [sentinel]
                    report.update(passed=True, blocked_actions=fixture.blocked, media_sentinel_preserved=True,
                                  media_subfolders_created=False, source_checks=fixture.source_checks,
                                  source_search_checks=fixture.search_checks, wiring_checks=fixture.wiring_checks)
                    browser.close()
        print("Setup journey browser checks passed: " + str(output))
    except Exception as exc:
        report["failure"] = str(exc)
        if "fixture" in locals():
            report["blocked_actions"] = fixture.blocked
        if page is not None:
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
        raise
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(10)
        listener.close()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
