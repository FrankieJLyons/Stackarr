"""Add the four core apps to an owned Plex preview using an actual packaged controller."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.docker_runtime import executable

PORTS = {"qbittorrent": 42460, "sonarr": 42461, "radarr": 42462, "prowlarr": 42463}
VERIFY = '''
import json
import httpx
from pathlib import Path
from stackarr.store import Store
store=Store(Path('/var/lib/stackarr'))
config=store.config()[1]
result={}
with httpx.Client(timeout=15,trust_env=False,follow_redirects=False) as client:
    for key,path in [('sonarr','/data/media/tv'),('radarr','/data/media/movies')]:
        app=config.integrations[key]
        headers={'X-Api-Key':store.secret(key)['api_key']}
        roots=client.get(app.url+'/api/v3/rootfolder',headers=headers)
        roots.raise_for_status()
        assert [row['path'] for row in roots.json()]==[path]
        clients=client.get(app.url+'/api/v3/downloadclient',headers=headers)
        clients.raise_for_status()
        rows=clients.json()
        assert len(rows)==1 and rows[0]['name']=='Stackarr qBittorrent'
        fields={f['name']:f.get('value') for f in rows[0]['fields']}
        assert fields['host']=='host.docker.internal' and fields['port']==42460
        assert fields['tvCategory' if key=='sonarr' else 'movieCategory']==key
        result[key]={'root_folder':path,'download_clients':len(rows)}
    app=config.integrations['prowlarr']
    headers={'X-Api-Key':store.secret('prowlarr')['api_key']}
    response=client.get(app.url+'/api/v1/applications',headers=headers)
    response.raise_for_status()
    apps=response.json()
    assert {row['implementation'] for row in apps}=={'Sonarr','Radarr'} and len(apps)==2
    for row in apps:
        fields={f['name']:f.get('value') for f in row['fields']}
        key=row['implementation'].lower()
        assert fields['baseUrl']==config.integrations[key].peer_url
        assert fields['prowlarrUrl']==app.peer_url
        assert row['syncLevel']=='addOnly'
    sources=client.get(app.url+'/api/v1/indexer',headers=headers)
    sources.raise_for_status()
    assert sources.json()==[]
    result['prowlarr']={'applications':len(apps),'indexers':0}
    app=config.integrations['qbittorrent']
    headers={'Referer':app.url}
    login=client.post(app.url+'/api/v2/auth/login',data=store.secret('qbittorrent'),headers=headers)
    assert login.status_code==204 or (login.status_code==200 and login.text.strip()=='Ok.')
    prefs=client.get(app.url+'/api/v2/app/preferences',headers=headers)
    prefs.raise_for_status()
    assert prefs.json()['save_path'].rstrip('/')=='/data/downloads'
    response=client.get(app.url+'/api/v2/torrents/categories',headers=headers)
    response.raise_for_status()
    categories=response.json()
    assert {key:value['savePath'].rstrip('/') for key,value in categories.items()}=={'sonarr':'/data/downloads/sonarr','radarr':'/data/downloads/radarr'}
    torrents=client.get(app.url+'/api/v2/torrents/info',headers=headers)
    torrents.raise_for_status()
    assert torrents.json()==[]
    result['qbittorrent']={'categories':sorted(categories),'downloads':0,'default_path':'/data/downloads'}
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true", help="Recheck the already installed batch without another installation")
    args = parser.parse_args()
    lab, package = args.lab.resolve(), args.package.resolve()
    if not lab.is_relative_to(Path("test-results").resolve()) or lab.is_symlink():
        parser.error("Choose an owned lab inside this workspace's test-results.")
    original = json.loads((lab / "report.json").read_text(encoding="utf-8-sig"))
    access = json.loads((lab / "access.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((package / "manifest.json").read_text())
    project, compose_path = original["project"], lab / "compose.json"
    assert project == "stackarr-plex-lab-" + lab.name.removeprefix("docker-plex-")
    assert original["passed"] and original["kept_running"]
    origin = access["dashboard"]
    assert urlsplit(origin).hostname == "localhost" and urlsplit(origin).port == 29100
    controller_root = lab / "controller"
    exe = package / "StackarrPreview.exe"
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == manifest["files"][exe.name]
    if not args.verify_existing:
        for port in PORTS.values():
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
    docker = executable()

    def command(arguments, timeout=120, stdin=None):
        result = subprocess.run([docker, *arguments], capture_output=True, text=True, encoding="utf-8",
                                input=stdin, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Scoped Docker preview operation failed; private output was withheld.")
        return result.stdout.strip()

    base = ["compose", "--project-name", project, "-f", str(compose_path)]
    before = set(command(["ps", "-q"]).splitlines())
    previous_dashboard = command([*base, "ps", "-q", "stackarr"])
    # Keep this fingerprint in memory only; no credential or digest enters reports.
    fingerprint = "import hashlib,sqlite3; d=sqlite3.connect('/var/lib/stackarr/stackarr.db'); r=d.execute(\"SELECT value FROM secrets WHERE name='plex'\").fetchone(); print(hashlib.sha256(r[0]).hexdigest())"
    plex_secret = command([*base, "exec", "-T", "stackarr", "python", "-c", fingerprint])
    sentinels = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (lab / "media").rglob("*") if path.is_file()}
    with httpx.Client(base_url=origin, trust_env=False, timeout=50, headers={"Origin": origin}) as client:
        login = client.post("/api/login", json={"password": access["owner_password"]})
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        assert not any(op["state"] in {"queued", "running", "failed", "interrupted"} for op in client.get("/api/deployments").json()["operations"])
        plex_config = client.get("/api/config").json()["config"]["integrations"]["plex"]
        assert plex_config["enabled"]
    command(["load", "--input", str(package / "stackarr-image.tar")])
    assert command(["image", "inspect", manifest["image"], "--format", "{{.Id}}"] ) == manifest["image_id"]
    environment = os.environ.copy()
    environment["STACKARR_LAB_CONTROLLER_ROOT"] = str(controller_root)
    # No filesystem operations or shell-built process commands; exact owned root only.
    stop = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name='StackarrPreview.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:STACKARR_LAB_CONTROLLER_ROOT) -and $_.CommandLine.Contains('--controller-serve') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                          env=environment, capture_output=True, text=True, timeout=20)
    if stop.returncode:
        raise RuntimeError("The owned preview controller could not be stopped.")
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", 29010), timeout=.2):
                pass
        except OSError:
            break
        time.sleep(.25)
    else:
        raise RuntimeError("The controller port is still occupied; no replacement was started.")
    environment.update(STACKARR_PORT="29100", STACKARR_CONTROLLER_ROOTS=json.dumps([
        {"path": str(lab / "media"), "host_path": str(lab / "media"), "label": "Plex test media"}]))
    with (lab / "core-controller.log").open("w", encoding="utf-8") as log:
        worker = subprocess.Popen([str(exe), "--controller-serve", str(controller_root), "--controller-port", "29010"],
                                  env=environment, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    access["controller_pid"] = worker.pid
    (lab / "access.json").write_text(json.dumps(access, indent=2), encoding="utf-8")
    compose = json.loads(compose_path.read_text())
    assert set(compose["services"]) == {"stackarr"}
    compose["services"]["stackarr"]["image"] = manifest["image"]
    compose_path.write_text(json.dumps(compose, indent=2))
    command([*base, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=150)
    print("Updated packaged dashboard and controller started; opening the add-app flow.", flush=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(45000)
        page.goto(origin)
        page.get_by_label("Password", exact=True).fill(access["owner_password"])
        page.get_by_role("button", name="Sign in", exact=False).click()
        page.get_by_role("button", name="Resume setup", exact=True).click()
        if args.verify_existing:
            operations = page.request.get(origin + "/api/deployments").json()["operations"]
            operation = next(op for op in operations if set(op["apps"]) == set(PORTS))
            assert operation["state"] == "needs-setup"
            identity = operation["id"]
            page.locator("#wiring-preview").click()
            expect(page.locator("#wiring-output")).to_contain_text("No new connections are ready to add", timeout=120000)
        else:
            page.get_by_role("button", name="Add another app", exact=True).click()
            for key in PORTS:
                page.locator("#setup-" + key).check()
            page.get_by_label("Port selection", exact=True).select_option("custom")
            for key, port in PORTS.items():
                page.get_by_label(({"qbittorrent": "qBittorrent", "sonarr": "Sonarr", "radarr": "Radarr", "prowlarr": "Prowlarr"}[key]) + " port", exact=True).fill(str(port))
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Choose a folderâ€¦", exact=True).click()
            page.get_by_role("button", name="Plex test media", exact=True).click()
            page.get_by_role("button", name="Use this folder", exact=True).click()
            page.get_by_role("button", name="Save & continue", exact=False).click()
            page.get_by_role("button", name="Review installation", exact=True).click()
            page.get_by_role("button", name="Download & install these apps", exact=True).click()
            print("Four-app installation approved in the browser; waiting for owned apps to start.", flush=True)
            for _ in range(360):
                operations = page.request.get(origin + "/api/deployments").json()["operations"]
                operation = next((op for op in operations if set(op["apps"]) == set(PORTS)), None)
                if operation and operation["state"] in {"needs-setup", "failed", "interrupted"}:
                    break
                page.wait_for_timeout(2000)
            assert operation and operation["state"] == "needs-setup"
            print("Owned apps started; checking private handoff and reviewed connections.", flush=True)
            identity = operation["id"]
            page.get_by_role("button", name="Check progress", exact=True).click()
            page.get_by_role("button", name="Finish connecting", exact=True).click()
            expect(page.locator("#wiring-preview")).to_be_visible()
            page.locator("#wiring-preview").click()
            expect(page.locator("#wiring-apply")).to_be_visible()
            page.locator("#wiring-apply").click()
            expect(page.locator("#wiring-output")).to_contain_text("Connection results", timeout=120000)
            assert page.locator("#wiring-output").inner_text().count(": created") == 4
            page.locator("#wiring-preview").click()
            expect(page.locator("#wiring-output")).to_contain_text("No new connections are ready to add")
        page.get_by_role("button", name="Review app login setup", exact=True).click()
        with page.expect_response(lambda response: response.url.endswith("/api/app-logins/apply")) as login_apply:
            page.get_by_role("button", name="Prepare and save app logins", exact=True).click()
        assert login_apply.value.status == 200
        assert [row["state"] for row in login_apply.value.json()["apps"]] == ["ready"] * 3
        expect(page.get_by_text("Generated login saved privately.", exact=False).first).to_be_visible()
        page.screenshot(path=str(lab / "core-connections.png"), full_page=True)
        browser.close()
    with httpx.Client(base_url=origin, trust_env=False, timeout=50, headers={"Origin": origin}) as client:
        login = client.post("/api/login", json={"password": access["owner_password"]})
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        config = client.get("/api/config").json()
        assert config["config"]["integrations"]["plex"] == plex_config
        assert set(config["credentials_saved"]) == set(PORTS) | {"plex"}
        client.post("/api/refresh").raise_for_status()
        for _ in range(60):
            states = client.get("/api/status").json()["integrations"]
            ready = {app["id"] for app in states if app["state"] == "ready" and not app["stale"]}
            if ready >= set(PORTS) | {"plex"}:
                break
            time.sleep(.5)
        else:
            raise RuntimeError("Fresh monitoring did not reach all five apps.")
        repeat = client.post("/api/deployments/" + identity + "/finish-connecting")
        repeat.raise_for_status()
        assert {app["state"] for app in repeat.json()["apps"]} == {"saved"}
        assert client.get("/api/wiring/preview").json()["changes"] == []
        for key in ("sonarr", "radarr", "prowlarr"):
            login_response = client.post("/api/apps/" + key + "/login", json={"password": access["owner_password"]})
            login_response.raise_for_status()
            credential = login_response.json()
            assert credential["username"] == "stackarr" and len(credential["password"]) >= 32
            assert credential["password"] not in client.get("/api/deployments").text
    verified = json.loads(command([*base, "exec", "-T", "stackarr", "python", "-c", VERIFY]))
    assert command([*base, "exec", "-T", "stackarr", "python", "-c", fingerprint]) == plex_secret
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in sentinels.items())
    assert before - {previous_dashboard} <= set(command(["ps", "-q"]).splitlines())
    report = {"passed": True, "deployment": identity, "ports": PORTS, "image": manifest["image_id"],
              "packaged_controller": True, "browser_flow": "existing batch verification" if args.verify_existing else "add-app installation", "fresh_monitoring": sorted(ready),
              "connections_created": 4, "repeat_proposes_changes": 0, "plex_preserved": True,
              "generated_arr_logins_verified": ["sonarr", "radarr", "prowlarr"],
              "media_and_unrelated_containers_preserved": True, "readback": verified,
              "scope": "Local Docker setup and connections; no indexers, media requests, downloads or import fixtures selected"}
    (lab / "core-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Packaged four-app setup passed; evidence: " + str(lab / "core-report.json"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        location = next(frame for frame in reversed(traceback.extract_tb(exc.__traceback__)) if frame.filename == __file__)
        raise SystemExit("Four-app preview check stopped (" + type(exc).__name__ + ", " + Path(location.filename).name
                         + ":" + str(location.lineno) + "). Owned data is retained; private output was withheld.") from None
