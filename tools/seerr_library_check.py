"""Verify original Seerr requests reached the correct Plex libraries and request availability."""

import json
import time

import httpx

from stackarr.deployment import Deployments
from stackarr.deployment_check import differences, inspect_container, load_receipt
from stackarr.finish_setup import read_candidate
from stackarr.store import Store
from tools.seerr_request_fixture import MAIN, ROOT


def main():
    imports = json.loads((ROOT / "imports-report.json").read_text())
    assert imports["passed"] and imports["season_episodes_imported"] == 6
    deployment = Deployments(Store(MAIN / "controller/state"))
    credentials = {}
    for key, identity in (("plex", "b06fec92071147f7aa7389a2df252759"),
                          ("seerr", json.loads((MAIN / "seerr-install-report.json").read_text())["deployment"])):
        payload = load_receipt(deployment, identity)
        info = inspect_container(deployment, identity, payload, key)
        assert not differences(info, "stackarr-owned-" + identity, key, payload["compose"]["services"][key])
        credentials[key] = read_candidate(deployment, identity, payload, key, deployment.store.config()[1].integrations[key])
    with httpx.Client(base_url="http://127.0.0.1:42450", trust_env=False, timeout=60,
                      headers={"X-Plex-Token": credentials["plex"]["api_key"], "Accept": "application/json"}) as plex, \
         httpx.Client(base_url="http://127.0.0.1:42464", trust_env=False, timeout=60,
                      headers={"X-Api-Key": credentials["seerr"]["api_key"]}) as seerr:
        identity = plex.get("/identity").json()["MediaContainer"]["machineIdentifier"]
        assert identity == "2a53c6f38fe655b611fbd80c5cf6409bb526300e"
        response = plex.get("/library/sections")
        response.raise_for_status()
        sections = response.json()["MediaContainer"]["Directory"]
        assert {row["title"] for row in sections} == {"Test Movies", "Test TV"}
        for section in sections:
            plex.get("/library/sections/" + section["key"] + "/refresh").raise_for_status()
        deadline = time.monotonic() + 240
        found = {}
        while time.monotonic() < deadline:
            for section in sections:
                response = plex.get("/library/sections/" + section["key"] + "/all", params={"includeGuids": 1})
                response.raise_for_status()
                for row in response.json()["MediaContainer"].get("Metadata", []):
                    wanted = "tmdb://10331" if section["type"] == "movie" else "tmdb://2316"
                    if any(item["id"] == wanted for item in row.get("Guid", [])):
                        found[section["type"]] = row
            if set(found) == {"movie", "show"} and found["show"].get("leafCount") == 6:
                break
            time.sleep(2)
        assert set(found) == {"movie", "show"} and found["show"].get("leafCount") == 6
        for key, row in found.items():
            response = plex.get("/library/metadata/" + row["ratingKey"] + ("/allLeaves" if key == "show" else ""))
            response.raise_for_status()
            files = [part["file"] for item in response.json()["MediaContainer"].get("Metadata", [])
                     for media in item.get("Media", []) for part in media.get("Part", [])]
            assert len(files) == (6 if key == "show" else 1) and all("StackarrFixture" in path for path in files)
        print("Plex sees the original movie and all six episode files in the correct test libraries.", flush=True)
        # Advance the supported library scan instead of waiting for its scheduled interval.
        seerr.post("/api/v1/settings/plex/sync", json={"start": True}).raise_for_status()
        requests = json.loads((ROOT / "requests.json").read_text())
        deadline = time.monotonic() + 240
        results = {}
        while time.monotonic() < deadline:
            results = {kind: seerr.get("/api/v1/request/" + str(identity)).json() for kind, identity in requests.items()}
            if all(row.get("status") == 5 for row in results.values()):
                break
            time.sleep(2)
        assert all(row.get("status") == 5 for row in results.values())
        assert results["movie"]["media"]["status"] == 5
        assert results["tv"]["media"]["status"] in (4, 5)
        assert all(season["status"] == 5 for season in results["tv"]["seasons"])
        counts = seerr.get("/api/v1/request/count").json()
        result = {"passed": True, **imports, "docker_plex_identity_verified": True,
                  "plex_movie_visible": True, "plex_season_episodes_visible": 6,
                  "seerr_requests_completed": 2, "seerr_request_counts": counts,
                  "supported_library_scan_triggered": True,
                  "scope": "Original bars/silence using known metadata stand-ins; Seerr requests -> local private BitTorrent -> automatic import -> Plex libraries -> completed requests. No named work is included."}
        (ROOT / "flow-report.json").write_text(json.dumps(result, indent=2))
        print("Both Seerr requests completed with Plex library visibility; full original-media flow passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        frame = next(frame for frame in reversed(traceback.extract_tb(exc.__traceback__)) if frame.filename == __file__)
        raise SystemExit(f"Seerr library check stopped ({type(exc).__name__}, line {frame.lineno}); private state retained.") from None
