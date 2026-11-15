"""Read real APIs in a prepared Docker lab; never configures media applications."""

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from stackarr.config import CATALOG, Integration
from stackarr.integrations import IntegrationError, collect
from tools.docker_lab import LAB_APPS, PORTS, lab_plan


def docker(context, *arguments):
    result = subprocess.run(["docker", "--context", context, *arguments], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    if result.returncode:
        raise ValueError("Lab Docker read failed; inspect the selected lab container locally.")
    return result.stdout


def verified_lab(directory, context):
    directory = directory.resolve()
    if not re.fullmatch(r"stackarr-lab-[a-f0-9]{12}", directory.name):
        raise ValueError("Only an explicitly prepared Stackarr lab is supported")
    receipt = json.loads((directory / "lab.json").read_text())
    if receipt["project"] != directory.name or set(receipt["apps"]) - set(LAB_APPS):
        raise ValueError("Lab receipt mismatch")
    payload = (directory / "compose.json").read_text(encoding="utf-8").encode()
    if hashlib.sha256(payload).hexdigest() != receipt["compose_sha256"]:
        raise ValueError("Lab plan changed; review and prepare a new lab")
    compose = json.loads(payload)
    if compose != lab_plan(directory, compose["services"]["stackarr"]["image"], receipt["apps"]):
        raise ValueError("Lab plan does not match the isolated template")
    endpoint = docker(context, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}").strip()
    if not endpoint.startswith(("npipe:////./pipe/", "unix:///")):
        raise ValueError("Lab requires a local Docker context")
    containers = {}
    for app in ["stackarr", *receipt["apps"]]:
        name = f"{directory.name}-{app}-1"
        info = json.loads(docker(context, "inspect", name))[0]
        labels = info["Config"]["Labels"]
        if labels.get("com.docker.compose.project") != directory.name or labels.get("com.docker.compose.service") != app:
            raise ValueError("Container ownership mismatch")
        if set(info["NetworkSettings"]["Networks"]) != {directory.name + "_control"}:
            raise ValueError("Lab container attached to an unexpected network")
        if info["HostConfig"]["Privileged"] or info["HostConfig"].get("PidMode") == "host":
            raise ValueError("Lab container has unexpected host privileges")
        expected_mounts = compose["services"][app]["volumes"]
        for mount in info["Mounts"]:
            if mount["Type"] == "bind":
                expected = next((m for m in expected_mounts if m["type"] == "bind" and m["target"] == mount["Destination"]), None)
                if not expected or Path(mount["Source"]).resolve() != Path(expected["source"]).resolve():
                    raise ValueError("Lab container has an unexpected host mount")
                if mount["RW"] == expected.get("read_only", False):
                    raise ValueError("Lab mount permission mismatch")
            elif mount["Type"] == "volume":
                # Plex declares its own anonymous /transcode volume in the upstream image.
                if app == "plex" and mount["Destination"] == "/transcode" and re.fullmatch(r"[a-f0-9]{64}", mount["Name"]):
                    continue
                expected = next((m for m in expected_mounts if m["type"] == "volume" and m["target"] == mount["Destination"]), None)
                if not expected or mount["Name"] != directory.name + "_" + expected["source"]:
                    raise ValueError("Lab container has an unexpected data volume")
        internal_port = PORTS[app] if app in ("stackarr", "qbittorrent") else CATALOG[app]["port"]
        if app == "stackarr":
            internal_port = 8787
        port = info["NetworkSettings"]["Ports"].get(str(internal_port) + "/tcp")
        if not port or any(p["HostIp"] != "127.0.0.1" or int(p["HostPort"]) != PORTS[app] for p in port):
            raise ValueError("Lab port mapping mismatch")
        containers[app] = {"name": name, "image_id": info["Image"], "running": info["State"]["Running"]}
    return receipt, containers


async def check(directory, context):
    receipt, containers = verified_lab(directory, context)
    results = {}
    for app in receipt["apps"]:
        secret = {}
        if app in ("sonarr", "radarr", "prowlarr"):
            xml = docker(context, "exec", containers[app]["name"], "cat", "/config/config.xml")
            secret = {"api_key": ET.fromstring(xml).findtext("ApiKey")}
        elif app == "qbittorrent":
            saved = docker(context, "exec", containers["stackarr"]["name"], "python", "-c",
                           "import json; from pathlib import Path; from stackarr.store import Store; "
                           "print(json.dumps(Store(Path('/var/lib/stackarr')).secret('qbittorrent')))")
            secret = json.loads(saved)
            # Capture only in memory: upstream logs can contain a temporary credential.
            if not secret.get("password"):
                logs = docker(context, "logs", containers[app]["name"])
                matches = re.findall(r"temporary password is provided for this session: (\S+)", logs)
                if matches:
                    secret = {"username": "admin", "password": matches[-1]}
        integration = Integration(enabled=True, url=f"http://127.0.0.1:{PORTS[app]}")
        try:
            tables = await collect(app, integration, secret)
            results[app] = {"state": "collector-passed", "tables": {k: len(v) for k, v in tables.items()}}
        except IntegrationError as exc:
            results[app] = {"state": "needs-setup", "code": exc.code}
        except (httpx.HTTPError, ValueError, TypeError):
            results[app] = {"state": "failed", "code": "api-check-failed"}
    with httpx.Client(trust_env=False, timeout=10) as client:
        base = f"http://localhost:{PORTS['stackarr']}"
        response = client.get(base + "/healthz")
        response.raise_for_status()
        assert response.json()["status"] == "ok"
        assert client.get(base + "/api/config").status_code == 401
    sentinel = directory / "media" / "preserve.txt"
    preserved = hashlib.sha256(sentinel.read_bytes()).hexdigest() == receipt["sentinel_sha256"]
    result = {"scope": "Real isolated Docker API checks; no Plex claim, playback, downloads or reboot test",
              "stackarr": "health-and-auth-boundary-passed", "media_sentinel_preserved": preserved,
              "apps": results, "containers": containers}
    (directory / "api-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--context", required=True)
    args = parser.parse_args()
    result = asyncio.run(check(args.directory, args.context))
    print(json.dumps({"stackarr": result["stackarr"], "apps": result["apps"],
                      "media_sentinel_preserved": result["media_sentinel_preserved"]}, indent=2))


if __name__ == "__main__":
    main()
