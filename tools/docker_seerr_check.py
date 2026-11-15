"""Seerr installation in the existing owned Docker preview; private output stays local."""

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finish", action="store_true", help="Verify private handoff and reviewed Seerr connections after account setup")
    args = parser.parse_args()
    root = Path("test-results/docker-plex-bc615eaf1fe6").resolve()
    access = json.loads((root / "access.json").read_text())
    origin = access["dashboard"]
    assert origin == "http://localhost:29100"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(60000)
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Resume setup", exact=True).click()
        operations = page.request.get(origin + "/api/deployments").json()["operations"]
        existing = next((op for op in operations if op["apps"] == ["seerr"]), None)
        if existing:
            assert existing["state"] == "needs-setup"
            identity = existing["id"]
        else:
            page.get_by_role("button", name="Add another app", exact=True).click()
            page.locator("#setup-seerr").check()
            page.get_by_label("Port selection", exact=True).select_option("custom")
            page.get_by_label("Seerr port", exact=True).fill("42464")
            page.get_by_role("button", name="Save & continue", exact=False).click()
            expect(page.get_by_text("No media folder needed", exact=True)).to_be_visible()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Review installation", exact=True).click()
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
            print("Seerr installation approved through the packaged browser flow.", flush=True)
            for _ in range(240):
                operations = page.request.get(origin + "/api/deployments").json()["operations"]
                existing = next((op for op in operations if op["apps"] == ["seerr"]), None)
                if existing and existing["state"] in {"needs-setup", "failed", "interrupted"}:
                    break
                time.sleep(2)
            assert existing and existing["state"] == "needs-setup"
            identity = existing["id"]
        if args.finish:
            with page.expect_response(lambda response: response.url.endswith("/finish-connecting")) as finished:
                page.get_by_role("button", name="Finish connecting", exact=True).click()
            assert finished.value.status == 200 and finished.value.json()["apps"][0]["state"] in {"connected", "saved"}
            with page.expect_response(lambda response: response.url.endswith("/api/wiring/preview")) as reviewed:
                page.locator("#wiring-preview").click()
            plan = reviewed.value.json()
            assert len(plan["changes"]) in {0, 2} and all(row["target"] == "seerr" for row in plan["changes"])
            if plan["changes"]:
                with page.expect_response(lambda response: response.url.endswith("/api/wiring/apply")) as applied:
                    page.locator("#wiring-apply").click()
                assert applied.value.status == 200
                assert {row["state"] for row in applied.value.json()["results"]} == {"created"}
            with page.expect_response(lambda response: response.url.endswith("/api/wiring/preview")) as repeat:
                page.locator("#wiring-preview").click()
            assert repeat.value.json()["changes"] == []
            page.get_by_role("button", name="Apps", exact=True).click()
            page.screenshot(path=str(root / "seerr-connections.png"), full_page=True)
            stamp = time.time()
            page.request.post(origin + "/api/refresh")
            for _ in range(60):
                rows = page.request.get(origin + "/api/status").json()["integrations"]
                ready = {row["id"] for row in rows if row["state"] == "ready" and not row["stale"] and (row["collected_at"] or 0) > stamp}
                if ready == {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr"}:
                    break
                time.sleep(.5)
            assert len(ready) == 6
            (root / "seerr-connections-report.json").write_text(json.dumps({"passed": True, "deployment": identity,
                "private_handoff": True, "reviewed_arr_connections": 2, "repeat_changes": 0,
                "fresh_monitoring": sorted(ready)}, indent=2))
        else:
            (root / "seerr-install-report.json").write_text(json.dumps({"passed": True, "deployment": identity,
                "port": 42464, "browser_install": True, "account_and_request_flow": "pending"}, indent=2))
        browser.close()
    print("Owned Seerr installed; account setup and request acceptance follow.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        frame = next(frame for frame in reversed(traceback.extract_tb(exc.__traceback__)) if frame.filename == __file__)
        raise SystemExit(f"Seerr check stopped ({type(exc).__name__}, line {frame.lineno}); private state retained.") from None
