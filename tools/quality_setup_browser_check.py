"""Exercise library/quality setup in an isolated browser with synthetic local state."""

import argparse
import json
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from stackarr import onboarding
from stackarr.pairing import PairingGate
from stackarr.server import create_app
from tools.browser_check import resume_setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    media = output / "test-media"
    media.mkdir()
    sentinel = media / "preserve.txt"
    sentinel.write_text("Synthetic test media sentinel.", encoding="utf-8")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    pairing = PairingGate()
    app = create_app(output / "state", origin=origin, pairing=pairing,
        media_roots=[{"path": str(media), "host_path": str(media), "label": "Alpha test media"}])
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            page.get_by_role("button", name="Request setup approval").click()
            page.get_by_text("Your code:", exact=False).wait_for()
            assert pairing.approve(pairing.display_code())
            page.get_by_label("Create a password", exact=True).fill("synthetic quality test password")
            page.get_by_role("button", name="Continue to setup").click()
            page.get_by_role("button", name="Movies & TV · recommended", exact=True).click()
            page.get_by_role("button", name="Save & continue").click()
            expect(page.get_by_label("Movies request quality", exact=True)).to_have_value("HD-1080p")
            expect(page.get_by_label("TV request quality", exact=True)).to_have_value("HD-1080p")
            expect(page.get_by_text(str(media / "media/movies"), exact=True)).to_be_hidden()
            page.get_by_text("See Movies folder location", exact=True).click()
            expect(page.get_by_text(str(media / "media/movies"), exact=True)).to_be_visible()
            expect(page.get_by_text(str(media / "media/tv"), exact=True)).to_be_hidden()
            page.get_by_text("See TV folder location", exact=True).click()
            expect(page.get_by_text(str(media / "media/tv"), exact=True)).to_be_visible()
            page.screenshot(path=str(output / "quality-desktop.png"), full_page=True)
            page.locator("section").filter(has=page.get_by_role("heading", name="Movies & TV", exact=True)).screenshot(
                path=str(output / "quality-library.png"))
            page.get_by_label("Movies request quality", exact=True).select_option("Ultra-HD")
            page.get_by_label("TV request quality", exact=True).select_option("other")
            expect(page.get_by_label("TV other quality", exact=True)).to_be_visible()
            page.get_by_label("TV other quality", exact=True).select_option("SD")
            page.get_by_role("button", name="Save & continue").click()
            expect(page.get_by_text("Request quality: Movies · 4K / UHD · TV · SD", exact=True)).to_be_visible()
            saved = onboarding.read(app.state.store)["draft"]
            assert saved["choices"]["radarr"]["quality_profile"] == "Ultra-HD"
            assert saved["choices"]["sonarr"]["quality_profile"] == "SD"
            page.reload()
            resume_setup(page)
            page.get_by_role("button", name="Back", exact=True).click()
            expect(page.get_by_label("Movies request quality", exact=True)).to_have_value("Ultra-HD")
            expect(page.get_by_label("TV request quality", exact=True)).to_have_value("other")
            expect(page.get_by_label("TV other quality", exact=True)).to_have_value("SD")
            page.get_by_label("TV other quality", exact=True).select_option("HD-720p")
            page.get_by_label("Movies request quality", exact=True).select_option("HD-1080p")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / "quality-phone.png"), full_page=True)
            page.get_by_role("button", name="Save & continue").click()
            expect(page.get_by_text("Request quality: Movies · 1080p · TV · 720p", exact=True)).to_be_visible()
            saved = onboarding.read(app.state.store)["draft"]
            assert saved["choices"]["sonarr"]["quality_profile"] == "HD-720p"
            page.get_by_role("button", name="Back", exact=True).click()
            page.get_by_role("button", name="Back", exact=True).click()
            page.get_by_text('Customize apps or connect existing apps', exact=True).click()
            page.get_by_label("Sonarr setup", exact=True).select_option("connect")
            page.get_by_label("Sonarr address", exact=True).fill("http://sonarr.example")
            page.get_by_role("button", name="Save & continue").click()
            expect(page.get_by_label("Movies request quality", exact=True)).to_be_visible()
            assert page.get_by_label("TV request quality", exact=True).count() == 0
            assert onboarding.read(app.state.store)["draft"]["choices"]["sonarr"]["quality_profile"] == ""
            assert sentinel.read_text(encoding="utf-8") == "Synthetic test media sentinel."
            assert not (media / "media").exists()
            assert not errors, errors
            browser.close()
        (output / "report.json").write_text(json.dumps({"passed": True, "scenarios": [
            "1080p defaults", "explicit movie and TV locations", "independent 4K and SD", "saved draft reload",
            "720p other choice", "mobile layout", "existing apps preserved", "no media writes"],
            "page_errors": errors}, indent=2), encoding="utf-8")
        print("Quality setup browser checks passed: " + str(output))
    finally:
        server.should_exit = True
        thread.join(10)


if __name__ == "__main__":
    main()
