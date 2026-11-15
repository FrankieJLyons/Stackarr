"""Real Docker update failure/restart injection in the fixed disposable core lab.

Faults live only in this maintainer tool. The product has no fault switch or arbitrary
image/command API. Candidate writes affect only this lab's Prowlarr configuration.
"""

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path

import httpx

from stackarr.app_backups import compatibility, digest
from stackarr.arr_logins import read as read_login
from stackarr.deployment import Deployments
from stackarr.deployment_check import inspect_container, load_receipt
from stackarr.store import Store
from stackarr.updates import Updates, catalog

ROOT = Path("test-results/docker-core-05cebfd84fd1")
IDENTITY = "c6903afb2218471aa2a45be825f625e5"


class TestInterruption(BaseException):
    pass


def settings(service, payload):
    data = {}
    for key in payload["apps"]:
        port = payload["compose"]["services"][key]["ports"][0]["published"]
        secret = service.store.secret(key)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=20) as client:
            if key == "qbittorrent":
                client.post("/api/v2/auth/login", data={"username": secret["username"], "password": secret["password"]}).raise_for_status()
                data[key] = client.get("/api/v2/app/preferences").json()
            else:
                client.headers["X-Api-Key"] = secret["api_key"]
                api = "/api/v1" if key == "prowlarr" else "/api/v3"
                data[key] = {"ui": client.get(api + "/config/ui").json()}
                if key in {"sonarr", "radarr"}:
                    rows = client.get(api + ("/series" if key == "sonarr" else "/movie")).json()
                    data[key]["library"] = [(row["id"], row["path"]) for row in rows]
                assert read_login(service, IDENTITY, payload, key, secret["api_key"])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recover", help="Fresh-process recovery for this tool's interrupted transaction")
    args = parser.parse_args()
    root = ROOT.resolve()
    controller_root = root / "package-state" / "controller" / "state"
    # Never reset a running packaged lab controller's job journal.
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 29014)) != 0, "Stop only the disposable lab controller before fault injection."
    service = Deployments(Store(controller_root))
    updater = Updates(service)
    if args.recover:
        run = updater.read(args.recover)
        assert run["deployment"] == IDENTITY and run["app"] == "prowlarr"
        result = updater.execute(updater.review(IDENTITY, "prowlarr", "update-recover", args.recover))
        assert result["state"] == "succeeded"
        print("Fresh controller process recovered the interrupted image/data transaction.")
        return
    payload = load_receipt(service, IDENTITY)
    assert set(payload["apps"]) == {"sonarr", "radarr", "prowlarr", "qbittorrent"}
    media = {path: digest(path) for path in (root / "media").rglob("*") if path.is_file()}
    original = compatibility(payload)
    for key in payload["apps"]:
        info = inspect_container(service, IDENTITY, payload, key)
        if not info["State"].get("Running"):
            service.actions.execute(service.actions.review(IDENTITY, key, "start"))
    for key in payload["apps"]:
        image = updater.image(payload, payload["compose"]["services"][key]["image"])
        version = image["Config"]["Labels"]["org.opencontainers.image.version"]
        assert updater.health(payload | {"identity": IDENTITY}, key, service.store.secret(key), version)
    expected = settings(service, payload)
    target = catalog()["apps"]["prowlarr"]["image"]
    normal_health = updater.health
    evidence = []
    for fault in ("health-failure", "controller-interruption"):
        written = False
        def inject(candidate, key, secret, version, seconds=180):
            nonlocal written
            passed = normal_health(candidate, key, secret, version, seconds)
            if candidate["compose"]["services"][key]["image"] != target or not passed:
                return passed
            port = candidate["compose"]["services"][key]["ports"][0]["published"]
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"X-Api-Key": secret["api_key"]}, trust_env=False) as client:
                config = client.get("/api/v1/config/ui").json()
                config["showRelativeDates"] = not config["showRelativeDates"]
                client.put("/api/v1/config/ui", json=config).raise_for_status()
            info = updater.owned(IDENTITY, candidate, key)
            service._call(["--context", candidate["context"]["name"], "exec", info["Id"], "/bin/sh", "-c", "printf 'original test mutation' > /config/stackarr-update-test-marker"])
            written = True
            if fault == "controller-interruption":
                raise TestInterruption()
            return False
        updater.health = inject
        try:
            outcome = updater.execute(updater.review(IDENTITY, "prowlarr"))
            assert fault == "health-failure" and outcome["state"] == "rolled-back"
        except TestInterruption:
            runs = updater.listing()["history"]
            identity = runs[0]["id"]
            run = updater.read(identity)
            assert run["backup"] and written
            # Model the exact file/database commit gap, then start a new controller process.
            updater.save(run, "running", "committing-receipt")
            (controller_root / "deployments" / IDENTITY / "compose.json").write_text(json.dumps(run["new"]["compose"], sort_keys=True))
            subprocess.run([sys.executable, "-m", "tools.docker_update_fault_check", "--recover", identity], check=True, timeout=300)
        updater.health = normal_health
        assert written
        payload = load_receipt(service, IDENTITY)
        assert compatibility(payload) == original
        current = settings(service, payload)
        assert current == expected, "Restored settings, credentials or library records differ."
        info = inspect_container(service, IDENTITY, payload, "prowlarr")
        marker = service._call(["--context", payload["context"]["name"], "exec", info["Id"], "/bin/sh", "-c", "if test -e /config/stackarr-update-test-marker; then printf present; else printf absent; fi"])
        assert marker == "absent"
        for path, checksum in media.items():
            assert digest(path) == checksum
        evidence.append({"fault": fault, "candidate_changed_database_and_config": True,
                         "old_image_and_settings_recovered": True, "generated_logins_preserved": True,
                         "library_records_preserved": True, "media_hashes_preserved": len(media)})
        print(f"Real Docker {fault} recovery passed; image, settings, logins and media verified.", flush=True)
    for key in payload["apps"]:
        service.actions.execute(service.actions.review(IDENTITY, key, "stop"))
    (root / "update-fault-report.json").write_text(json.dumps({"passed": True, "cases": evidence,
        "test_apps_stopped": True, "volumes_and_media_preserved": True}, indent=2))


if __name__ == "__main__":
    main()
