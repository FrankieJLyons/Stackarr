"""Full Seerr request acceptance with original movie/season stand-ins in the owned lab."""

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path

import httpx

from stackarr.bootstrap import accepted
from stackarr.deployment import Deployments, images
from stackarr.deployment_check import differences, inspect_container, load_receipt
from stackarr.finish_setup import read_candidate
from stackarr.store import Store

MAIN = Path("test-results/docker-plex-bc615eaf1fe6").resolve()
ROOT = Path("test-results/docker-seerr-request-20261017").resolve()
OLD = Path("test-results/docker-core-05cebfd84fd1").resolve()
PROJECT = "stackarr-import-fixture-05cebfd84fd1"
CORE = "6aab7fcfffd645e6a56bcb9a760acb8c"
PORTS = {"sonarr": 42461, "radarr": 42462, "prowlarr": 42463, "seerr": 42464}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "source", "request", "verify", "cleanup"))
    args = parser.parse_args()
    assert ROOT.is_relative_to(Path("test-results").resolve()) and not ROOT.is_symlink()
    deployment = Deployments(Store(MAIN / "controller/state"))
    receipts = {}
    for identity in (CORE, "b06fec92071147f7aa7389a2df252759", json.loads((MAIN / "seerr-install-report.json").read_text())["deployment"]):
        payload = load_receipt(deployment, identity)
        for key in payload["apps"]:
            info = inspect_container(deployment, identity, payload, key)
            assert not differences(info, "stackarr-owned-" + identity, key, payload["compose"]["services"][key])
            receipts[key] = (identity, payload)
    assert set(receipts) == {"plex", "qbittorrent", *PORTS}
    fixtures = json.loads((ROOT / "seed-media/fixtures.json").read_text())
    assert len(fixtures) == 7
    for row in fixtures:
        with (ROOT / "seed-media" / row["filename"]).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"]
    keyfile = ROOT / "seed-media/fixture-key"
    if not keyfile.exists():
        keyfile.write_text(secrets.token_urlsafe(32))
    fixture_key = keyfile.read_text()
    compose_path = ROOT / "fixture-compose.json"
    base = ["compose", "--project-name", PROJECT, "-f", str(compose_path)]
    if args.phase == "prepare":
        state = ROOT / "fixture-state"
        state.mkdir(exist_ok=True)
        previous = json.loads((OLD / "fixture-compose.json").read_text())
        assert previous["services"]["fixture-seeder"]["image"] == images()["qbittorrent"]
        compose = previous
        compose["services"]["fixture-source"]["image"] = "stackarr:seerr-preview-20261017"
        compose["services"]["fixture-source"]["volumes"][1]["source"] = str(ROOT / "seed-media")
        compose["services"]["fixture-source"]["volumes"][2]["source"] = str(state)
        compose["services"]["fixture-seeder"]["volumes"].append({"type": "bind", "source": str(ROOT / "seed-media"), "target": "/requests", "read_only": True})
        compose["volumes"]["seeder-config"] = {"external": True, "name": PROJECT + "_seeder-config"}
        compose["networks"]["control"]["name"] = "stackarr-owned-" + CORE + "_control"
        compose_path.write_text(json.dumps(compose, sort_keys=True))
        deployment._call([*base, "up", "-d", "--wait", "--wait-timeout", "120"], timeout=150)
        time.sleep(2)
        url = "http://127.0.0.1:42491"
        with httpx.Client(base_url=url, trust_env=False, timeout=20, headers={"Referer": url}) as client:
            # Reuse the already verified durable credential; never read temporary logs.
            assert accepted(client.post("/api/v2/auth/login", data=json.loads((OLD / "fixture-access.json").read_text())))
            known = client.get("/api/v2/torrents/info").json()
            for row in fixtures:
                if not any(item["hash"] == row["hash"] for item in known):
                    client.post("/api/v2/torrents/add", files={"torrents": (str(row["id"]) + ".torrent", (ROOT / "seed-media" / (str(row["id"]) + ".torrent")).read_bytes())},
                                data={"savepath": "/requests", "skip_checking": "true", "stopped": "false", "autoTMM": "false"}).raise_for_status()
                client.post("/api/v2/torrents/setForceStart", data={"hashes": row["hash"], "value": "true"}).raise_for_status()
            for _ in range(30):
                torrents = client.get("/api/v2/torrents/info").json()
                if all(any(item["hash"] == row["hash"] and item["progress"] == 1 for item in torrents) for row in fixtures):
                    break
                time.sleep(.5)
            assert all(any(item["hash"] == row["hash"] and item["progress"] == 1 for item in torrents) for row in fixtures)
        print("Original movie and full six-episode season are available from the isolated seeder.")
        return
    clients = {}
    for key, port in PORTS.items():
        credential = deployment.store.secret(key)
        if key == "seerr":
            identity, payload = receipts[key]
            credential = read_candidate(deployment, identity, payload, key, deployment.store.config()[1].integrations[key])
        assert credential.get("api_key")
        clients[key] = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=60,
                                   headers={"X-Api-Key": credential["api_key"]})

    def request(key, method, path, **kwargs):
        response = clients[key].request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    if args.phase == "source":
        access = json.loads((MAIN / "access.json").read_text())
        with httpx.Client(base_url=access["dashboard"], trust_env=False, timeout=60, headers={"Origin": access["dashboard"]}) as client:
            response = client.post("/api/login", json={"password": access["owner_password"]})
            response.raise_for_status()
            client.headers["X-CSRF-Token"] = response.json()["csrf"]
            reviewed = client.post("/api/indexers/review", json={"name": "Stackarr Seerr original-media test", "feed_url": "http://fixture-source:8080/api", "api_key": fixture_key})
            reviewed.raise_for_status()
            result = client.post("/api/indexers/apply", json={"review_token": reviewed.json()["review_token"]})
            result.raise_for_status()
        sources = request("prowlarr", "GET", "/api/v1/indexer")
        source = next(row for row in sources if row["name"] == "Stackarr Seerr original-media test")
        (ROOT / "source.json").write_text(json.dumps({"id": source["id"], "name": source["name"]}))
        for _ in range(60):
            counts = {key: len(request(key, "GET", "/api/v3/indexer")) for key in ("sonarr", "radarr")}
            if all(counts.values()):
                break
            time.sleep(1)
        assert all(counts.values())
        print("The original-media source passed Stackarr's review/test/save and reached both Arr apps.")
        return
    checkpoint = ROOT / "requests.json"
    if args.phase == "request":
        if not (ROOT / "quality-before.json").exists():
            (ROOT / "quality-before.json").write_text(json.dumps({key: request(key, "GET", "/api/v3/qualitydefinition") for key in ("sonarr", "radarr")}, sort_keys=True))
        saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        for kind, media_id in (("movie", 10331), ("tv", 2316)):
            if kind in saved:
                continue
            details = request("seerr", "GET", f"/api/v1/{kind}/{media_id}")
            assert not (details.get("mediaInfo") or {}).get("requests")
            body = {"mediaType": kind, "mediaId": media_id}
            if kind == "tv":
                body["seasons"] = [1]
                assert next(row for row in details["seasons"] if row["seasonNumber"] == 1)["episodeCount"] == 6
            result = request("seerr", "POST", "/api/v1/request", json=body)
            saved[kind] = result["id"]
            checkpoint.write_text(json.dumps(saved, indent=2))
            print("Submitted the original " + kind + " request through Seerr; no direct Arr add/grab/import call was used.", flush=True)
        return
    if args.phase == "verify":
        saved = json.loads(checkpoint.read_text())
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            movie = next((row for row in request("radarr", "GET", "/api/v3/movie") if row["tmdbId"] == 10331), None)
            series = next((row for row in request("sonarr", "GET", "/api/v3/series") if row["tvdbId"] == 73244), None)
            episodes = request("sonarr", "GET", "/api/v3/episode", params={"seriesId": series["id"]}) if series else []
            episodes = [row for row in episodes if row["seasonNumber"] == 1]
            if movie and movie.get("hasFile") and len(episodes) == 6 and all(row.get("hasFile") for row in episodes):
                break
            time.sleep(2)
        assert movie and movie.get("hasFile") and len(episodes) == 6 and all(row.get("hasFile") for row in episodes)
        imports = [("radarr", movie["movieFile"], fixtures[0])]
        for episode in sorted(episodes, key=lambda row: row["episodeNumber"]):
            data = request("sonarr", "GET", "/api/v3/episodefile/" + str(episode["episodeFileId"]))
            imports.append(("sonarr", data, fixtures[episode["episodeNumber"]]))
        for key, data, row in imports:
            path = MAIN / "media" / Path(data["path"].removeprefix("/data/"))
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"]
            history = request(key, "GET", "/api/v3/history", params={"pageSize": 100})["records"]
            assert any(item["eventType"] == "downloadFolderImported" and item.get("downloadId", "").lower() == row["hash"] for item in history)
        before = json.loads((ROOT / "quality-before.json").read_text())
        assert all(request(key, "GET", "/api/v3/qualitydefinition") == before[key] for key in before)
        (ROOT / "imports-report.json").write_text(json.dumps({"passed": True, "movie_imported": True,
            "season_episodes_imported": 6, "all_hashes_match": True, "quality_settings_unchanged": True,
            "direct_arr_add_grab_or_manual_import": False, "request_ids": saved}, indent=2))
        print("Seerr's movie and season requests automatically downloaded/imported; all seven hashes match.")
        return
    if args.phase == "cleanup":
        assert json.loads((ROOT / "flow-report.json").read_text())["passed"]
        source = json.loads((ROOT / "source.json").read_text())
        rows = request("prowlarr", "GET", "/api/v1/indexer")
        selected = next((row for row in rows if row["id"] == source["id"]), None)
        if selected:
            fields = {row["name"]: row.get("value") for row in selected["fields"]}
            assert selected["name"] == source["name"] and fields["baseUrl"] == "http://fixture-source:8080"
            request("prowlarr", "DELETE", "/api/v1/indexer/" + str(source["id"]))
        for key in ("sonarr", "radarr"):
            for row in request(key, "GET", "/api/v3/indexer"):
                if row["name"] == source["name"] + " (Prowlarr)":
                    fields = {field["name"]: field.get("value") for field in row["fields"]}
                    assert fields["baseUrl"].startswith("http://host.docker.internal:42463")
                    request(key, "DELETE", "/api/v3/indexer/" + str(row["id"]))
        for service in ("fixture-source", "fixture-seeder"):
            info = json.loads(deployment._call(["inspect", PROJECT + "-" + service + "-1"]))[0]
            assert info["Config"]["Labels"]["com.docker.compose.project"] == PROJECT
        deployment._call([*base, "stop"], timeout=120)
        url = "http://127.0.0.1:42460"
        with httpx.Client(base_url=url, trust_env=False, timeout=20, headers={"Referer": url}) as client:
            assert accepted(client.post("/api/v2/auth/login", data=deployment.store.secret("qbittorrent")))
            rows = client.get("/api/v2/torrents/info").json()
            hashes = {row["hash"] for row in fixtures}
            assert all(any(item["hash"] == value and item["progress"] == 1 for item in rows) for value in hashes)
            client.post("/api/v2/torrents/stop", data={"hashes": "|".join(sorted(hashes))}).raise_for_status()
        (ROOT / "cleanup-report.json").write_text(json.dumps({"passed": True, "temporary_source_removed": True,
            "fixture_containers_stopped": 2, "test_torrents_stopped_without_deletion": 7,
            "sample_media_and_evidence_retained": True, "main_apps_preserved": True}, indent=2))
        print("Stopped the fixture services and seven test torrents without deleting files; removed only the temporary source.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        frame = next(frame for frame in reversed(traceback.extract_tb(exc.__traceback__)) if frame.filename == __file__)
        raise SystemExit(f"Seerr request check stopped ({type(exc).__name__}, line {frame.lineno}); private state retained.") from None
