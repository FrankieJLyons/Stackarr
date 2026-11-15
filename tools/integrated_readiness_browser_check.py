"""Browser acceptance for integrated readiness; installer/process calls are fixtures."""

import argparse
import contextlib
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr import first_run_docker
from stackarr.first_run import DOCKER_GUIDE, inspect
from stackarr.first_run_package import PackageStart
from stackarr.first_run_server import ReadinessServer
from tools.first_run_docker_browser_check import check as prerequisite_cases


@contextlib.contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


class Destination(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        body = b"<!doctype html><h1>Isolated destination ready</h1>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    prior = prerequisite_cases(output / "prerequisite-fixtures")
    cases = list(prior["cases"])
    calls, installed, engine = [], [False], [False]
    facts = {"windows": True, "build": 26100, "workstation": True, "architecture": "AMD64",
             "memory": 16 * 1024**3, "hypervisor": True}

    def inspector(mode):
        return inspect(mode, facts_reader=lambda: facts, space_reader=lambda: 30 * 1024**3,
            runtime_reader=lambda **_: {"state": "ready" if engine[0] else "needs-attention", "guide": DOCKER_GUIDE,
                "checks": [{"check": "docker", "ok": installed[0], "detail": "Docker found." if installed[0] else "Docker not found."},
                           {"check": "engine", "ok": engine[0], "detail": "Open Docker Desktop and check again."}]})

    payload = b"Integrated prerequisite fixture, never executed"
    original = dict(first_run_docker.RELEASE)
    first_run_docker.RELEASE.update(sha256=hashlib.sha256(payload).hexdigest())

    def download(path, update, cancelled):
        calls.append("download")
        path.write_bytes(payload)
        update(len(payload))
        return True

    def install(path):
        calls.append("installer-fixture")
        installed[0] = True
        return 3010

    setup = first_run_docker.DockerSetup(output.resolve() / "prerequisites", exists=lambda: installed[0],
        downloader=download, signer=lambda _: calls.append("signature-fixture"), launcher=install,
        locker=lambda _: contextlib.nullcontext())
    try:
        with serving(ThreadingHTTPServer(("127.0.0.1", 0), Destination)) as destination, sync_playwright() as p:
            url = "http://127.0.0.1:" + str(destination.server_port) + "/#private-fixture"
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1320, "height": 1060})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def start(name, runner):
                return PackageStart(output.resolve() / "package", output.resolve() / (name + "-docker"),
                    output.resolve() / (name + "-connect"), runner=runner)

            launches = []
            handoff = start("install", lambda mode: launches.append(mode) or {"url": url})
            with serving(ReadinessServer(inspector, setup, handoff)) as server:
                page.goto(server.launch_url)
                expect(page.locator("#install-docker")).to_be_visible()
                expect(page.locator("#continue-stackarr")).to_be_hidden()
                page.locator("#install-docker").click()
                expect(page.get_by_role("dialog")).to_be_visible()
                assert not calls and not launches
                page.locator("#approve-docker").click()
                expect(page.locator("#docker-message")).to_contain_text("requested a Windows restart", timeout=15000)
                expect(page.locator("#continue-stackarr")).to_be_hidden()
                assert calls == ["download", "signature-fixture", "installer-fixture"] and not launches
                page.reload()
                expect(page.locator("#docker-message")).to_contain_text("requested a Windows restart")
                engine[0] = True
                page.locator("#retry").click()
                expect(page.locator("#continue-stackarr")).to_be_visible()
                page.screenshot(path=str(output / "ready-to-continue.png"), full_page=True)
                assert not handoff.state_root.exists()
                page.locator("#continue-stackarr").click()
                expect(page.get_by_role("heading", name="Isolated destination ready")).to_be_visible()
                assert launches == ["install"] and calls.count("installer-fixture") == 1
                cases.append("integrated-reviewed-docker-restart-recheck-and-same-tab-handoff")

            engine[0] = installed[0] = False
            handoff = start("connect", lambda mode: launches.append(mode) or {"url": url})
            with serving(ReadinessServer(inspector, setup, handoff)) as server:
                page.goto(server.launch_url)
                page.locator('input[value="connect"]').check()
                expect(page.locator("#continue-stackarr")).to_be_visible()
                expect(page.locator("#install-docker")).to_be_hidden()
                page.locator("#continue-stackarr").click()
                expect(page.get_by_role("heading", name="Isolated destination ready")).to_be_visible()
                assert launches == ["install", "connect"] and calls.count("installer-fixture") == 1
                assert not handoff.state_root.exists() and not handoff.connect_root.exists()
                cases.append("connect-existing-skips-docker-and-keeps-install-state-separate")

            engine[0] = installed[0] = True
            attempts = []
            def retry(mode):
                attempts.append(mode)
                if len(attempts) == 1:
                    return {"review": "reinstall"}
                if len(attempts) == 2:
                    raise OSError("Private error withheld")
                return {"url": url}
            handoff = start("retry", retry)
            with serving(ReadinessServer(inspector, setup, handoff)) as server:
                page.goto(server.launch_url)
                expect(page.locator("#continue-stackarr")).to_be_visible()
                engine[0] = False
                page.locator("#continue-stackarr").click()
                expect(page.locator("#setup-error")).to_contain_text("Check readiness again")
                assert not attempts
                cases.append("continuation-rechecks-stale-readiness-before-any-launch")
                engine[0] = True
                page.locator("#continue-stackarr").click()
                expect(page.locator("#next-step")).to_contain_text("Review reinstall")
                expect(page.locator("#continue-stackarr")).to_be_enabled()
                page.locator("#continue-stackarr").click()
                expect(page.locator("#setup-error")).to_contain_text("Stackarr could not open")
                assert "Private error" not in page.locator("#setup-error").inner_text()
                page.locator("#continue-stackarr").click()
                expect(page.get_by_role("heading", name="Isolated destination ready")).to_be_visible()
                assert attempts == ["install"] * 3
                cases.append("retained-installation-review-and-safe-launch-failure-allow-retry")
            assert not errors
            browser.close()
    finally:
        first_run_docker.RELEASE.clear()
        first_run_docker.RELEASE.update(original)
    result = {"passed": True, "cases": cases, "real_installer_executed": False,
              "scope": "Browser and real local readiness services; synthetic installer, prerequisites and package destination."}
    (output / "browser-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(check(parser.parse_args().output), indent=2))
