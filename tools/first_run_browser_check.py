"""Exercise only the independent readiness page; never contacts Docker."""

import argparse
import json
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr.first_run import DOCKER_GUIDE, inspect
from stackarr.first_run_server import ReadinessServer


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    scenario = ["missing"]
    probes = []
    facts = {"windows": True, "architecture": "AMD64", "build": 26100, "workstation": True,
             "memory": 16 * 1024**3, "hypervisor": True}

    def evaluate(mode):
        probes.append(mode)
        if scenario[0] == "failed":
            raise OSError("synthetic private error")
        ready = scenario[0] == "ready"
        return inspect(mode, facts_reader=lambda: facts, space_reader=lambda: 30 * 1024**3,
                       runtime_reader=lambda **_: {"state": "ready" if ready else "needs-attention", "guide": DOCKER_GUIDE, "checks": [
                           {"check": "docker", "ok": True, "detail": "Docker is installed."},
                           {"check": "engine", "ok": True, "detail": "The Linux x64 container engine is running."}]
                           if ready else [{"check": "docker", "ok": False, "detail": "Docker was not found. Install Docker using the official guide, then reopen Stackarr."}]})

    cases = []
    with ReadinessServer(evaluate) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width": 1320, "height": 1060})
                page = context.new_page()
                errors = []
                external = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.on("request", lambda req: external.append(req.url) if not req.url.startswith(server.origin + "/") else None)
                page.goto(server.launch_url)
                expect(page.get_by_role("heading", name="Install Docker Desktop to continue")).to_be_visible()
                expect(page.get_by_role("link", name="Get Docker Desktop", exact=False)).to_be_visible()
                expect(page.get_by_text("Docker was not found.", exact=False)).to_be_visible()
                expect(page.get_by_role("link", name="Open Docker setup guide", exact=False)).to_have_attribute("target", "_blank")
                assert page.url == server.origin + "/"
                page.screenshot(path=str(output / "missing-docker-desktop.png"), full_page=True)
                cases.append("missing-docker-and-official-next-step")
                page.reload()
                expect(page.get_by_role("heading", name="Install Docker Desktop to continue")).to_be_visible()
                cases.append("reload-retains-private-launch")
                scenario[0] = "ready"
                page.get_by_role("button", name="Check again").click()
                expect(page.get_by_role("heading", name="Ready for the next setup step")).to_be_visible()
                page.screenshot(path=str(output / "ready-desktop.png"), full_page=True)
                cases.append("retry-recovers-after-docker-starts")
                page.get_by_role("radio", name="Connect apps I already run", exact=False).check()
                expect(page.get_by_role("heading", name="Ready to connect existing apps")).to_be_visible()
                expect(page.locator("#checks .check")).to_have_count(1)
                cases.append("existing-app-path-skips-local-prerequisites")
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_role("radio", name="Install apps on this computer", exact=False).check()
                expect(page.get_by_role("heading", name="Ready for the next setup step")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / "ready-mobile.png"), full_page=True)
                cases.append("narrow-layout-without-horizontal-overflow")
                page.set_viewport_size({"width": 780, "height": 900})
                page.evaluate("document.documentElement.style.fontSize = '200%'")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("document.documentElement.style.fontSize = ''")
                page.get_by_role("button", name="Check again").focus()
                expect(page.get_by_role("button", name="Check again")).to_be_focused()
                cases.append("keyboard-focus-and-text-zoom")
                other = browser.new_context()
                stranger = other.new_page()
                before = len(probes)
                stranger.goto(server.origin)
                expect(stranger.get_by_role("heading", name="Reopen Stackarr readiness")).to_be_visible()
                assert len(probes) == before
                other.close()
                cases.append("separate-browser-cannot-trigger-host-checks")
                restricted = browser.new_context()
                restricted.add_init_script("Object.defineProperty(window, 'sessionStorage', {get() { throw new DOMException('Storage blocked', 'SecurityError'); }});")
                restricted_page = restricted.new_page()
                restricted_page.goto(server.launch_url)
                expect(restricted_page.get_by_role("heading", name="Ready for the next setup step")).to_be_visible()
                restricted.close()
                cases.append("blocked-browser-storage-still-checks-with-launch-capability")
                scenario[0] = "failed"
                page.get_by_role("button", name="Check again").click()
                expect(page.get_by_role("heading", name="Checks could not finish")).to_be_visible()
                assert "synthetic private error" not in page.locator("body").inner_text()
                scenario[0] = "ready"
                page.get_by_role("button", name="Check again").click()
                expect(page.get_by_role("heading", name="Ready for the next setup step")).to_be_visible()
                cases.append("redacted-failure-and-successful-retry")
                page.get_by_role("button", name="Close checks").click()
                expect(page.get_by_role("heading", name="Checks closed")).to_be_visible()
                cases.append("close-stops-only-the-checker")
                assert not errors and not external
                cases.append("no-script-errors-or-external-requests")
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
    report = {"passed": True, "cases": cases, "docker_contacted": False,
              "fixture": "Synthetic Windows/runtime states; separate from clean-PC acceptance."}
    (output / "browser-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    print(json.dumps(check(parser.parse_args().output), indent=2))
