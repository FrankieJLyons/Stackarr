"""Restart only a receipt-verified core batch and require fresh authenticated results."""

import argparse
import json
import time
from pathlib import Path

import httpx

from stackarr.deployment import Deployments
from stackarr.deployment_check import differences, inspect_container, load_receipt
from stackarr.store import Store
from tools.docker_core_check import PORTS, VERIFY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    args = parser.parse_args()
    lab = args.lab.resolve()
    assert lab.is_relative_to(Path("test-results").resolve()) and not lab.is_symlink()
    report = json.loads((lab / "core-report.json").read_text())
    access = json.loads((lab / "access.json").read_text())
    assert report["passed"] and report["ports"] == PORTS
    identity = report["deployment"]
    deployment = Deployments(Store(lab / "controller/state"))
    payload = load_receipt(deployment, identity)
    assert set(payload["apps"]) == set(PORTS)
    containers = {}
    for key in PORTS:
        info = inspect_container(deployment, identity, payload, key)
        assert not differences(info, "stackarr-owned-" + identity, key, payload["compose"]["services"][key])
        containers[key] = info["Id"]
    credentials = {key: deployment.store.secret(key) for key in PORTS}
    stamp = time.time()
    compose = deployment.store.root / "deployments" / identity / "compose.json"
    deployment._call(["--context", payload["context"]["name"], "compose", "--project-name", "stackarr-owned-" + identity,
                      "-f", str(compose), "restart"], timeout=120)
    origin = access["dashboard"]
    assert origin == "http://localhost:29100"
    with httpx.Client(base_url=origin, trust_env=False, timeout=50, headers={"Origin": origin}) as client:
        login = client.post("/api/login", json={"password": access["owner_password"]})
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        for _ in range(60):
            client.post("/api/refresh").raise_for_status()
            states = client.get("/api/status").json()["integrations"]
            ready = {app["id"] for app in states if app["state"] == "ready" and not app["stale"]
                     and (app["collected_at"] or 0) > stamp}
            if ready >= set(PORTS) | {"plex"}:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Fresh authenticated monitoring did not recover after restart.")
        assert client.get("/api/wiring/preview").json()["changes"] == []
    for key in PORTS:
        assert inspect_container(deployment, identity, payload, key)["Id"] == containers[key]
        assert deployment.store.secret(key) == credentials[key]
    original = json.loads((lab / "report.json").read_text())
    verified = json.loads(deployment._call(["exec", original["project"] + "-stackarr-1", "python", "-c", VERIFY]))
    result = {"passed": True, "deployment": identity, "restarted": sorted(PORTS),
              "same_containers": True, "credentials_preserved": True, "fresh_monitoring_after_restart": sorted(ready),
              "repeat_proposes_changes": 0, "readback": verified,
              "scope": "App-container restart only; no Windows reboot or signed-out startup certification"}
    (lab / "core-restart-report.json").write_text(json.dumps(result, indent=2))
    print("Owned four-app restart and fresh credential checks passed.")


if __name__ == "__main__":
    main()
