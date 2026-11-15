"""Exercise reviewed prerequisite setup with synthetic bytes and installer calls."""

import argparse
import contextlib
import hashlib
import json
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from stackarr import first_run_docker
from stackarr.first_run import DOCKER_GUIDE, inspect
from stackarr.first_run_server import ReadinessServer


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    payload = b"Synthetic prerequisite fixture; never executed"
    original = dict(first_run_docker.RELEASE)
    first_run_docker.RELEASE.update(sha256=hashlib.sha256(payload).hexdigest())
    go = threading.Event()
    installed = [False]
    calls = []
    facts = {"windows": True, "build": 26100, "workstation": True, "architecture": "AMD64",
             "memory": 16 * 1024**3, "hypervisor": True}

    def report(mode):
        return inspect(mode, facts_reader=lambda: facts, space_reader=lambda: 30 * 1024**3,
                       runtime_reader=lambda **_: {"state": "needs-attention", "guide": DOCKER_GUIDE, "checks": [
                           {"check": "docker", "ok": True, "detail": "Docker is installed."},
                           {"check": "engine", "ok": False, "detail": "Open Docker Desktop and check again."}]
                           if installed[0] else [{"check": "docker", "ok": False, "detail": "Docker was not found."}]})

    def download(path, update, cancelled):
        calls.append("download")
        while not go.wait(.05):
            if cancelled.is_set():
                return False
        path.write_bytes(payload)
        update(len(payload))
        return True

    def launch(path):
        calls.append("installer")
        installed[0] = True
        return 3010

    service = first_run_docker.DockerSetup(output.resolve() / "state", exists=lambda: installed[0],
                                          downloader=download, signer=lambda _: calls.append("signature"),
                                          launcher=launch, locker=lambda _: contextlib.nullcontext())
    cases = []
    try:
        with ReadinessServer(report, service) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page(viewport={"width": 1320, "height": 1060})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(server.launch_url)
                    page.get_by_role("button", name="Install Docker Desktop", exact=True).click()
                    expect(page.get_by_role("dialog")).to_be_visible()
                    expect(page.locator("#docker-release")).to_contain_text("for this Windows account")
                    assert not calls
                    page.screenshot(path=str(output / "review-installation.png"), full_page=True)
                    page.get_by_role("button", name="Go back", exact=True).click()
                    assert not calls
                    cases.append("review-and-go-back-have-no-download-or-install")
                    page.get_by_role("button", name="Install Docker Desktop", exact=True).click()
                    page.get_by_role("button", name="Download & install", exact=True).click()
                    expect(page.get_by_text("Downloading Docker Desktop from Docker's official server.", exact=True)).to_be_visible()
                    expect(page.get_by_role("button", name="Close checks", exact=True)).to_be_disabled()
                    page.get_by_role("button", name="Cancel download", exact=True).click()
                    expect(page.get_by_text("Download cancelled.", exact=False)).to_be_visible()
                    assert "installer" not in calls
                    cases.append("approved-download-progress-and-cancellation")
                    page.get_by_role("button", name="Install Docker Desktop", exact=True).click()
                    page.get_by_role("button", name="Download & install", exact=True).click()
                    go.set()
                    expect(page.get_by_text("Docker's installer requested a Windows restart.", exact=False)).to_be_visible(timeout=15000)
                    assert calls == ["download", "download", "signature", "installer"]
                    expect(page.get_by_role("button", name="Install Docker Desktop", exact=True)).to_be_hidden()
                    page.screenshot(path=str(output / "restart-needed.png"), full_page=True)
                    cases.append("verified-install-order-and-explicit-restart-guidance")
                    page.reload()
                    expect(page.get_by_text("Docker's installer requested a Windows restart.", exact=False)).to_be_visible()
                    assert calls.count("installer") == 1
                    cases.append("reopening-retains-outcome-without-reinstalling")
                    installed[0] = False
                    service.save("installing")
                    service.worker = None
                    page.reload()
                    expect(page.get_by_text("An earlier setup was interrupted.", exact=False)).to_be_visible()
                    page.get_by_role("button", name="Install Docker Desktop", exact=True).click()
                    expect(page.get_by_role("button", name="Download & install", exact=True)).to_be_disabled()
                    page.get_by_role("checkbox", name="I have completed or closed", exact=False).check()
                    expect(page.get_by_role("button", name="Download & install", exact=True)).to_be_enabled()
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(output / "interrupted-review-mobile.png"), full_page=True)
                    page.get_by_role("button", name="Go back", exact=True).click()
                    assert calls.count("installer") == 1
                    cases.append("interrupted-installer-requires-reviewed-acknowledgement")
                    assert not errors
                    browser.close()
            finally:
                go.set()
                server.shutdown()
                thread.join(timeout=3)
    finally:
        first_run_docker.RELEASE.clear()
        first_run_docker.RELEASE.update(original)
    result = {"passed": True, "cases": cases, "real_installer_executed": False,
              "fixture": "Synthetic bytes, signature and installer result; no Windows/Docker changes."}
    (output / "browser-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(check(parser.parse_args().output), indent=2))
