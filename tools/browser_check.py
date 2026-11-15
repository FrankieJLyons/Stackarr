"""Isolated real-browser smoke test: synthetic integrations, temporary state, loopback only."""
import argparse
import json
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import expect, sync_playwright

from stackarr.pairing import PairingGate
from stackarr.server import create_app


@contextmanager
def capture_browser_failure(get_page, output):
    """Capture synthetic UI diagnostics while Playwright is still running."""
    try:
        yield
    except Exception:
        try:
            page = get_page()
            print(json.dumps({'fixture_headings': page.get_by_role('heading').all_text_contents(),
                              'fixture_alerts': page.get_by_role('alert').all_text_contents()}))
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
        except Exception:
            pass  # Diagnostics must not replace the original failure.
        raise


def resume_setup(page):
    page.wait_for_function("() => document.querySelector('#setup-message') || document.querySelector('button[data-view=setup]')")
    if page.locator('#setup-message').is_visible():
        return
    page.get_by_role('button', name='Setup', exact=True).or_(
        page.get_by_role('button', name='Resume setup', exact=True)).click()


def open_server(page):
    page.locator('button[data-view="overview"]').click()


def open_task_group(page, name):
    if page.locator('.control-tabs').count():
        page.locator('button[data-view="setup"]').click()
        page.locator('.setup-tool-picker > summary').click()
        page.locator('.setup-tool-picker [data-setup-task="' + name + '"]').click()
        return
    group = page.locator('#setup-group-' + name)
    group.wait_for(state='attached')
    if not group.evaluate('element => element.open'):
        group.locator(':scope > summary').click()


def synthetic(request):
    path = request.url.path
    if request.url.host == "cleanuparr.example":
        return httpx.Response(200, json={"dryRun": True, "enabled": False, "searchEnabled": False, "proactiveSearchEnabled": False})
    if request.url.host == "seerr.example":
        if path in ('/api/v1/media', '/api/v1/request') or path.startswith('/api/v1/discover/'):
            return httpx.Response(200, json={'results': [], 'totalPages': 1, 'pageInfo': {'pages': 1}})
        if path.endswith("/status"):
            return httpx.Response(200, json={"version": "synthetic"})
        if path.endswith("/request/count"):
            return httpx.Response(200, json={"total": 2, "pending": 1, "approved": 1, "declined": 0, "processing": 0, "available": 1})
    if request.url.host == "radarr.example":
        return httpx.Response(401)
    if path.endswith("/system/status"):
        return httpx.Response(200, json={"version": "synthetic-test"})
    if path.endswith("/health"):
        return httpx.Response(200, json=[])
    if path.endswith("/queue"):
        return httpx.Response(200, json={"records": [
            {"title": "Example series · S01E03", "trackedDownloadState": "importPending", "id": 1},
            {"title": "Example series · S01E04", "trackedDownloadState": "importing", "id": 2}]})
    if path.endswith("/blocklist"):
        return httpx.Response(200, json={"records": []})
    if path.endswith("/indexer"):
        return httpx.Response(200, json=[{"name": "Synthetic test source", "enable": True, "protocol": "torrent"}])
    if path.endswith("/auth/login"):
        return httpx.Response(200, text="Ok.")
    if path.endswith("/torrents/info"):
        return httpx.Response(200, json=[{"name": "Public domain sample", "state": "downloading", "progress": .64}])
    if path.endswith("/status/sessions"):
        return httpx.Response(200, json={"MediaContainer": {"size": 1, "Metadata": [{"title": "Public domain sample", "Player": {"state": "playing"}}]}})
    raise AssertionError("Unexpected synthetic route")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-setup", action="store_true")
    args = parser.parse_args()
    output = Path("test-results")
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stackarr-ui-") as temp, socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        pairing = PairingGate()
        app = create_app(Path(temp), origin, httpx.MockTransport(synthetic), pairing=None if args.docker_setup else pairing)
        reserved.close()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            with sync_playwright() as playwright, capture_browser_failure(lambda: page, output):
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin)
                if args.docker_setup:
                    from stackarr.setup_handoff import issue
                    page.goto(issue(app.state.store, origin))
                else:
                    page.get_by_role("button", name="Request setup approval").click()
                    page.get_by_text("Your code:", exact=False).wait_for()
                    assert pairing.approve(pairing.display_code())
                password = "synthetic browser password"
                page.get_by_label("Create a password", exact=True).fill(password)
                page.get_by_role("button", name="Show password", exact=True).click()
                expect(page.get_by_label("Create a password", exact=True)).to_have_attribute("type", "text")
                page.get_by_role("button", name="Hide password", exact=True).click()
                expect(page.get_by_label("Create a password", exact=True)).to_have_attribute("type", "password")
                expect(page.locator("html")).to_have_attribute("data-accent", "blue")
                page.screenshot(path=str(output / "sign-in-blue-eye.png"), full_page=True)
                page.get_by_role("button", name="Continue to setup", exact=False).click()
                expect(page.get_by_role("heading", name="Setup", exact=True)).to_be_visible()
                page.get_by_role("button", name="Add app +", exact=True).click()
                page.get_by_role("button", name="Set up Plex", exact=True).click()
                page.get_by_label("How would you like to add Plex?", exact=True).select_option("connect")
                page.get_by_label("Plex address", exact=True).fill("http://plex.example")
                page.get_by_role("button", name="Continue to setup", exact=True).click()
                page.get_by_role("button", name="Save & continue", exact=False).click()
                page.get_by_role("button", name="Save & continue", exact=False).click()
                assert page.get_by_role("button", name="Review installation", exact=True).count() == 0
                page.get_by_role("button", name="Review existing app connections", exact=True).click()
                page.get_by_role("button", name="Save reviewed app addresses", exact=True).click()
                expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
                expect(page.locator("#plex-key")).to_be_visible()
                page.locator("#plex-key").fill("synthetic-plex-token")
                page.get_by_role("button", name="Save settings", exact=True).click()
                page.wait_for_function("() => !state.dirty && state.credentials.includes('plex')")
                page.locator('.control-tabs [data-view="overview"]').click()
                page.get_by_role("button", name="Refresh status", exact=False).click()
                expect(page.locator("#overview-apps")).to_contain_text("Connected", timeout=15000)
                page.locator('.control-tabs [data-view="settings"]').click()
                page.locator('[data-settings-section="appearance"]').click()
                page.get_by_label("App colour", exact=True).select_option("purple")
                page.get_by_label("Appearance", exact=True).select_option("light")
                page.get_by_label("Media storage", exact=True).uncheck()
                page.get_by_role("button", name="Save settings", exact=True).click()
                page.wait_for_function("() => !state.dirty && state.config.dashboard.accent==='purple'")
                expect(page.locator("html")).to_have_attribute("data-accent", "purple")
                page.get_by_role("button", name="Sign out", exact=True).click()
                page.reload()
                expect(page.locator("html")).to_have_attribute("data-accent", "purple")
                expect(page.locator("html")).to_have_attribute("data-theme", "light")
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign in", exact=False).click()
                expect(page.locator("#overview-apps")).to_be_visible()
                expect(page.locator('[data-widget="storage"]')).to_have_count(0)
                page.locator('.control-tabs [data-view="help"]').click()
                expect(page.get_by_role("heading", name="Help & FAQ", exact=True)).to_be_visible()
                page.locator('.control-tabs [data-view="setup"]').click()
                expect(page.get_by_role("heading", name="Your setup checklist", exact=True)).to_be_visible()
                for width, height in [(1440, 1000), (390, 844)]:
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                    page.screenshot(path=str(output / f"setup-refined-{width}.png"), full_page=True)
                assert not errors, errors
                browser.close()
                (output / "browser-report.json").write_text(json.dumps({"passed":True,"errors":errors,
                    "scope":"Real source API and UI; synthetic integration transport; no Docker or household app requests",
                    "checks":["setup approval","password eye","single app catalog","connect wizard","no install on connect path","connection settings save","live collector result","persisted palette and widget preferences","signed-out theme","help navigation","ordered checklist","phone layout"]},indent=2),encoding="utf-8")
                print("Browser smoke passed: real setup approval, app connection wizard, appearance persistence, sign-in, help and responsive checklist.")
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == "__main__":
    main()
