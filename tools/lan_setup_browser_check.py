"""Guided LAN browser acceptance in new synthetic state; no Docker or OS changes."""

import argparse
import json
import threading
from pathlib import Path

from cryptography import x509
from playwright.sync_api import expect, sync_playwright

from stackarr.lan_setup import LanSetup
from stackarr.lan_setup_server import LanSetupServer
from stackarr.self_update import write


def check(output, caddy):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state = output / "installation"
    state.mkdir()
    write(state / "installation.json", {"owner":"stackarr-docker-preview-v1", "port":29123})
    setup = LanSetup(state, output / "network", caddy.resolve(), network_reader=lambda:[
        {"name":"Home Ethernet", "address":"172.20.50.10", "clients":"172.20.50.0/24", "profile":"Private"}])
    calls = []

    class ReviewFixture:
        def review(self, action, identity=None):
            calls.append("review")
            return {"action":action, "network":identity, "notice":"Enable the reviewed address using an encrypted checkpoint. Local recovery stays available."}

    cases = []
    with LanSetupServer(setup) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={"width":1320, "height":1100})
                page = context.new_page()
                errors, external = [], []
                page.on("pageerror", lambda error:errors.append(str(error)))
                page.on("request", lambda request:external.append(request.url) if not request.url.startswith(server.origin + "/") else None)
                page.goto(server.launch_url)
                expect(page.locator("#address")).to_have_value("172.20.50.10")
                assert page.url == server.origin + "/"
                page.get_by_role("button", name="Prepare secure access", exact=True).click()
                expect(page.get_by_role("heading", name="Your address is saved")).to_be_visible(timeout=30000)
                expect(page.locator("#gateway-status")).to_contain_text("start secure access")
                page.screenshot(path=str(output / "prepared-desktop.png"), full_page=True)
                cases.append("real-caddy-preparation-without-activation")
                fingerprint = setup.status()["certificate"]["fingerprint"]
                page.reload()
                expect(page.get_by_role("heading", name="Your address is saved")).to_be_visible()
                assert setup.status()["certificate"]["fingerprint"] == fingerprint
                cases.append("reload-retains-private-launch-and-certificate")
                page.get_by_role("button", name="Connect a computer", exact=True).click()
                expect(page.get_by_role("heading", name="Connect another computer")).to_be_visible()
                for system, text in [("windows", "Trusted Root"), ("macos", "Keychain"), ("ios", "Certificate Trust"), ("android", "CA certificate"), ("firefox", "Authorities")]:
                    page.locator("#device-system").select_option(system)
                    expect(page.locator("#device-instructions")).to_contain_text(text)
                page.locator("#device-system").select_option("windows")
                with page.expect_download() as download:
                    page.get_by_role("button", name="Download public certificate").click()
                saved = output / "public-client.cer"
                download.value.save_as(saved)
                assert x509.load_der_x509_certificate(saved.read_bytes()).subject
                assert b"PRIVATE KEY" not in saved.read_bytes()
                cases.append("public-certificate-download-and-plain-language-trust-guide")
                page.set_viewport_size({"width":390,"height":844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / "certificate-mobile.png"), full_page=True)
                page.set_viewport_size({"width":780,"height":1000})
                page.evaluate("document.documentElement.style.fontSize='200%'")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("document.documentElement.style.fontSize=''")
                cases.append("mobile-text-zoom-and-unbroken-fingerprint")
                page.get_by_role("button", name="Recover access", exact=True).click()
                expect(page.get_by_role("link", name="Open on this computer")).to_have_attribute("href", "http://localhost:29123")
                page.screenshot(path=str(output / "recovery.png"), full_page=True)
                page.get_by_role("button", name="1 · Prepare access").click()
                page.get_by_text("What happens when I enable access?", exact=True).click()
                page.get_by_role("button", name="Review activation").click()
                expect(page.locator("#error")).to_contain_text("review an update")
                assert not (state / "stackarr-runtime.json").exists()
                cases.append("older-installation-is-not-adopted-by-opening-or-reviewing")
                write(state / "stackarr-runtime.json", {})
                setup.updates_factory = lambda _: ReviewFixture()
                page.get_by_role("button", name="Review activation").click()
                expect(page.get_by_role("dialog")).to_be_visible()
                page.get_by_role("button", name="Keep current settings").click()
                expect(page.get_by_role("dialog")).not_to_be_visible()
                assert calls == ["review"] and setup.saved["job"] is None
                cases.append("review-cancel-keeps-settings-and-physical-checks-pending")
                other = browser.new_context()
                stranger = other.new_page()
                stranger.goto(server.origin)
                expect(stranger.locator("#message")).to_contain_text("Reopen Home network")
                expect(stranger.get_by_role("button", name="Prepare secure access")).to_be_disabled()
                other.close()
                cases.append("unlaunched-browser-cannot-act")
                assert setup.status()["physical_status"] == "pending" and not setup.child
                page.get_by_role("button", name="Finish and stop this gateway").click()
                expect(page.locator("#message")).to_contain_text("Setup finished")
                assert not errors and not external
                cases.append("scoped-close-no-script-errors-no-external-requests")
                browser.close()
        finally:
            server.shutdown()
            thread.join(3)
            setup.stop()
    report = {"passed":True, "cases":cases, "docker_contacted":False,
              "physical_checks":"pending", "scope":"Synthetic installation and interfaces; real Caddy preparation, local browser UI, no listeners outside loopback or host changes."}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--caddy",type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.output,args.caddy),indent=2))
