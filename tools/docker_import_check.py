"""Original-media transfer and automatic Arr import in a disposable packaged Docker lab."""

import argparse
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from stackarr.bootstrap import accepted
from stackarr.deployment import Deployments, images
from stackarr.deployment_check import differences, inspect_container, load_receipt
from stackarr.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    parser.add_argument("--phase", choices=("prepare", "source", "search", "flow", "all"), default="all")
    args = parser.parse_args()
    root = args.lab.resolve()
    assert root.is_relative_to(Path("test-results").resolve()) and root.name.startswith("docker-core-")
    report = json.loads((root / "report.json").read_text())
    access = json.loads((root / "access.json").read_text())
    assert report["passed"] and report["kept_running"] and access["dashboard"] == "http://localhost:29140"
    deployment = Deployments(Store(root / "package-state/controller/state"))
    identity = report["deployment"]
    payload = load_receipt(deployment, identity)
    assert set(payload["apps"]) == {"sonarr", "radarr", "prowlarr", "qbittorrent"}
    ports = {}
    for key, expected in (("qbittorrent", 42470), ("sonarr", 42471), ("radarr", 42472), ("prowlarr", 42473)):
        info = inspect_container(deployment, identity, payload, key)
        assert not differences(info, "stackarr-owned-" + identity, key, payload["compose"]["services"][key])
        ports[key] = int(payload["compose"]["services"][key]["ports"][0]["published"])
        assert ports[key] == expected
    credentials = {key: deployment.store.secret(key) for key in ports}
    fixtures = json.loads((root / "seed-media/fixtures.json").read_text())
    assert len(fixtures) == 2
    for row in fixtures:
        with (root / "seed-media" / row["filename"]).open("rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == row["sha256"]
    project = "stackarr-import-fixture-" + root.name.removeprefix("docker-core-")
    fixture_state = root / "fixture-state"
    fixture_state.mkdir(exist_ok=True)
    fixture_key_path = root / "seed-media/fixture-key"
    if not fixture_key_path.exists():
        with fixture_key_path.open("x") as output:
            output.write(secrets.token_urlsafe(32))
    fixture_key = fixture_key_path.read_text()
    compose = {"services": {
        "fixture-source": {"image": "stackarr:import-preview-20261017", "entrypoint": ["python", "-u", "/fixture.py"],
            "command": ["/fixtures", "--public-url", "http://fixture-source:8080", "--events", "/state/events.jsonl"],
            "ports": ["127.0.0.1:42490:8080"], "cap_drop": ["ALL"], "read_only": True,
            "security_opt": ["no-new-privileges:true"], "networks": ["control"], "healthcheck": {"disable": True},
            "volumes": [{"type": "bind", "source": str(Path("tools/torznab_fixture.py").resolve()), "target": "/fixture.py", "read_only": True},
                        {"type": "bind", "source": str(root / "seed-media"), "target": "/fixtures", "read_only": True},
                        {"type": "bind", "source": str(fixture_state), "target": "/state"}]},
        "fixture-seeder": {"image": images()["qbittorrent"], "ports": ["127.0.0.1:42491:42491"],
            "environment": {"PUID": "1000", "PGID": "1000", "WEBUI_PORT": "42491", "TZ": "Etc/UTC"},
            "security_opt": ["no-new-privileges:true"], "networks": ["control"],
            "volumes": [{"type": "volume", "source": "seeder-config", "target": "/config"},
                        {"type": "bind", "source": str(root / "seed-media"), "target": "/seed", "read_only": True}]}
    }, "volumes": {"seeder-config": {}}, "networks": {"control": {"external": True, "name": "stackarr-owned-" + identity + "_control"}}}
    compose_path = root / "fixture-compose.json"
    rendered = json.dumps(compose, sort_keys=True)
    if compose_path.exists():
        assert compose_path.read_text() == rendered
    else:
        compose_path.write_text(rendered)
    base = ["compose", "--project-name", project, "-f", str(compose_path)]
    if args.phase in {"prepare", "all"}:
        deployment._call([*base, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=150)
        for _ in range(30):
            try:
                if httpx.get("http://127.0.0.1:42490/health", trust_env=False, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        seeder_name = project + "-fixture-seeder-1"
        info = json.loads(deployment._call(["inspect", seeder_name]))[0]
        assert info["Config"]["Labels"]["com.docker.compose.project"] == project and info["Config"]["Image"] == images()["qbittorrent"]
        private = root / "fixture-access.json"
        saved = json.loads(private.read_text()) if private.exists() else {"username": "admin", "password": secrets.token_urlsafe(32)}
        if not private.exists():
            private.write_text(json.dumps(saved))
        base_url = "http://127.0.0.1:42491"
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False, headers={"Referer": base_url}) as client:
            logged_in = False
            for _ in range(30):
                try:
                    logged_in = accepted(client.post(base_url + "/api/v2/auth/login", data=saved))
                    if logged_in:
                        break
                    logs = deployment._call(["logs", "--tail", "100", seeder_name])
                    temporary = re.findall(r"temporary password is provided for this session: (\S+)", logs)
                    if temporary and accepted(client.post(base_url + "/api/v2/auth/login", data={"username": "admin", "password": temporary[-1]})):
                        response = client.post(base_url + "/api/v2/app/setPreferences", data={"json": json.dumps({"web_ui_password": saved["password"]})})
                        response.raise_for_status()
                        logged_in = True
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            assert logged_in
            client.post(base_url + "/api/v2/app/setPreferences", data={"json": json.dumps({"dht": False, "pex": False, "lsd": False, "listen_port": 6881})}).raise_for_status()
            known = client.get(base_url + "/api/v2/torrents/info").json()
            for row in fixtures:
                if not any(item["hash"] == row["hash"] for item in known):
                    response = client.post(base_url + "/api/v2/torrents/add", files={"torrents": (str(row["id"]) + ".torrent", (root / "seed-media" / (str(row["id"]) + ".torrent")).read_bytes())},
                        data={"savepath": "/seed", "skip_checking": "true", "stopped": "false", "paused": "false", "autoTMM": "false"})
                    response.raise_for_status()
                client.post(base_url + "/api/v2/torrents/setForceStart", data={"hashes": row["hash"], "value": "true"}).raise_for_status()
            for _ in range(40):
                torrents = client.get(base_url + "/api/v2/torrents/info").json()
                if len(torrents) == 2 and all(row["progress"] == 1 for row in torrents):
                    break
                time.sleep(.5)
            assert len(torrents) == 2 and all(row["progress"] == 1 for row in torrents)
        print("Local source and private seeder are ready with two original fixtures.", flush=True)
    if args.phase in {"source", "all"}:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(120000)
            page.goto(access["dashboard"])
            page.get_by_label("Password", exact=True).fill(access["owner_password"])
            page.get_by_role("button", name="Sign in", exact=False).click()
            page.get_by_role("button", name="Apps", exact=True).click()
            page.get_by_text("Connect an existing Torznab feed", exact=True).click()
            page.get_by_label("Source name", exact=True).fill("Stackarr original-media test source")
            page.get_by_label("Torznab feed address", exact=True).fill("http://fixture-source:8080/api")
            page.get_by_label("Provider key (if required)", exact=True).fill(fixture_key)
            page.get_by_role("button", name="Review source", exact=True).click()
            page.get_by_role("button", name="Test and connect source", exact=True).click()
            expect(page.get_by_text("Source tested and saved in Prowlarr.", exact=False)).to_be_visible(timeout=120000)
            page.screenshot(path=str(root / "source-setup.png"), full_page=True)
            browser.close()
        print("Source tested and saved through the guided Stackarr browser flow.", flush=True)
    clients = {}
    for key in ("sonarr", "radarr", "prowlarr"):
        clients[key] = httpx.Client(base_url=f"http://127.0.0.1:{ports[key]}", timeout=60, trust_env=False,
                                   headers={"X-Api-Key": credentials[key]["api_key"]})
    if args.phase == "prepare":
        return
    for _ in range(90):
        source_counts = {key: len(clients[key].get("/api/v3/indexer").json()) for key in ("sonarr", "radarr")}
        if all(count == 1 for count in source_counts.values()):
            break
        time.sleep(1)
    assert source_counts == {"sonarr": 1, "radarr": 1}
    if args.phase == "source":
        print("The source was automatically shared to both Arr apps.")
        return
    def request(key, method, path, **kwargs):
        response = clients[key].request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    # Only this disposable lab's selected test quality has its size floor relaxed.
    for key in ("sonarr", "radarr"):
        for row in request(key, "GET", "/api/v3/qualitydefinition"):
            if row["quality"]["name"] == "WEBDL-720p" and row["minSize"] != 0:
                row["minSize"] = 0
                request(key, "PUT", "/api/v3/qualitydefinition/" + str(row["id"]), json=row)
    movies = request("radarr", "GET", "/api/v3/movie")
    movie = next((row for row in movies if row["tmdbId"] == 10331), None)
    if not movie:
        found = request("radarr", "GET", "/api/v3/movie/lookup", params={"term": "tmdb:10331"})[0]
        found.update(qualityProfileId=request("radarr", "GET", "/api/v3/qualityprofile")[0]["id"], rootFolderPath="/data/media/movies",
                     monitored=False, minimumAvailability="announced", addOptions={"searchForMovie": False})
        movie = request("radarr", "POST", "/api/v3/movie", json=found)
    series = next((row for row in request("sonarr", "GET", "/api/v3/series") if row["tvdbId"] == 73244), None)
    if not series:
        found = request("sonarr", "GET", "/api/v3/series/lookup", params={"term": "tvdb:73244"})[0]
        found.update(qualityProfileId=request("sonarr", "GET", "/api/v3/qualityprofile")[0]["id"], rootFolderPath="/data/media/tv",
                     monitored=False, seasonFolder=True, addOptions={"searchForMissingEpisodes": False, "monitor": "none"})
        series = request("sonarr", "POST", "/api/v3/series", json=found)
    for _ in range(90):
        episode = next((row for row in request("sonarr", "GET", "/api/v3/episode", params={"seriesId": series["id"]})
                        if row["seasonNumber"] == 1 and row["episodeNumber"] == 1), None)
        if episode:
            break
        time.sleep(1)
    assert episode
    if args.phase == "search":
        for key, query in (("radarr", {"movieId": movie["id"]}), ("sonarr", {"episodeId": episode["id"]})):
            wanted = fixtures[0 if key == "radarr" else 1]
            releases = request(key, "GET", "/api/v3/release", params=query)
            assert any(row["title"] == wanted["release"] for row in releases)
        print("Both Arr apps found their exact original fixture through the shared source; nothing was grabbed.")
        return
    qbit_url = "http://127.0.0.1:42470"
    qbit = httpx.Client(base_url=qbit_url, timeout=15, trust_env=False, headers={"Referer": qbit_url})
    assert accepted(qbit.post("/api/v2/auth/login", data=credentials["qbittorrent"]))
    qbit.post("/api/v2/app/setPreferences", data={"json": json.dumps({"dht": False, "pex": False, "lsd": False})}).raise_for_status()
    for key, target, query in (("radarr", movie, {"movieId": movie["id"]}), ("sonarr", episode, {"episodeId": episode["id"]})):
        wanted = fixtures[0 if key == "radarr" else 1]
        if any(row["hash"] == wanted["hash"] for row in qbit.get("/api/v2/torrents/info").json()):
            continue
        releases = request(key, "GET", "/api/v3/release", params=query)
        release = next(row for row in releases if row["title"] == wanted["release"])
        request(key, "POST", "/api/v3/release", json=release)
        print("The " + key + " fixture was grabbed through its Prowlarr source.", flush=True)
    stamp = time.monotonic()
    while time.monotonic() - stamp < 360:
        movie_state = request("radarr", "GET", "/api/v3/movie/" + str(movie["id"]))
        episode_state = request("sonarr", "GET", "/api/v3/episode/" + str(episode["id"]))
        if movie_state.get("hasFile") and episode_state.get("hasFile"):
            break
        time.sleep(2)
    assert movie_state.get("hasFile") and episode_state.get("hasFile")
    torrents = qbit.get("/api/v2/torrents/info").json()
    assert len(torrents) == 2 and all(row["progress"] == 1 for row in torrents)
    imported = []
    for key, data, row in (("radarr", movie_state["movieFile"], fixtures[0]),
                           ("sonarr", request("sonarr", "GET", "/api/v3/episodefile/" + str(episode_state["episodeFileId"])), fixtures[1])):
        path = root / "media" / Path(data["path"].removeprefix("/data/"))
        with path.open("rb") as source:
            assert hashlib.file_digest(source, "sha256").hexdigest() == row["sha256"]
        history = request(key, "GET", "/api/v3/history", params={"page": 1, "pageSize": 100})["records"]
        assert any(item["eventType"] == "downloadFolderImported" and item.get("downloadId", "").lower() == row["hash"] for item in history)
        torrent_row = next(item for item in torrents if item["hash"] == row["hash"])
        assert torrent_row["downloaded"] >= row["size"]
        imported.append({"app": key, "hash_matches_original": True, "automatic_import": True, "bytes_transferred": torrent_row["downloaded"],
                         "imported_path": data["path"], "category": torrent_row["category"]})
    result = {"passed": True, "fixtures": imported, "source_shared": source_counts, "private_torrents": True,
              "seed_and_download_are_separate_containers": True, "manual_import_commands_used": False,
              "scope": "Original colour bars/silence transferred over local BitTorrent and automatically imported; lab-only size floors relaxed for small generated videos. Known film/series names are metadata stand-ins only."}
    (root / "import-report.json").write_text(json.dumps(result, indent=2))
    print("Both original fixtures downloaded and were automatically imported; hashes match.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        location = next(frame for frame in reversed(traceback.extract_tb(exc.__traceback__)) if frame.filename == __file__)
        raise SystemExit("Import check stopped (" + type(exc).__name__ + ", line " + str(location.lineno)
                         + "). Isolated state retained; private output withheld.") from None
