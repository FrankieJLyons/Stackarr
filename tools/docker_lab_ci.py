"""Opt-in real-container fixture runner. Uses only a newly prepared Docker lab."""

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from stackarr.bundled_images import catalog, verify
from tools.docker_lab import LAB_APPS, PORTS, prepare
from tools.docker_lab_check import check, docker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--image", default="stackarr:ci")
    args = parser.parse_args()
    endpoint = docker(args.context, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}").strip()
    if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
        raise SystemExit("Only a local Docker lab is supported")
    for port in PORTS.values():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    image = docker(args.context, "image", "inspect", args.image, "--format", "{{.Id}}").strip()
    directory = prepare(Path("test-results/docker-lab"), image, list(LAB_APPS))
    command = ["docker", "--context", args.context, "compose", "--project-name", directory.name,
               "-f", str(directory / "compose.json")]
    bundled = catalog()
    for app in set(LAB_APPS) & bundled.keys():
        verify(lambda arguments: docker(args.context, *arguments), bundled[app]['image'])
    registry_apps = [app for app in LAB_APPS if app not in bundled]
    try:
        # Registry rate limits are transient and do not justify replaying app writes.
        for attempt in range(3):
            pulled = subprocess.run([*command, "pull", "--policy", "missing", *registry_apps], timeout=300)
            if pulled.returncode == 0:
                break
            if attempt == 2:
                pulled.check_returncode()
            time.sleep(10 * (attempt + 1))
        subprocess.run([*command, "up", "-d", "--pull", "never", "--wait", "--wait-timeout", "180"], check=True, timeout=600)
        subprocess.run([sys.executable, "-m", "tools.docker_lab_wire", str(directory),
                        "--context", args.context, "--apply"], check=True, timeout=180)
        subprocess.run([*command, "restart"], check=True, timeout=120)
        subprocess.run([*command, "up", "-d", "--pull", "never", "--wait", "--wait-timeout", "180"], check=True, timeout=240)
        # Services without healthchecks may still be initializing after restart.
        for _ in range(12):
            result = asyncio.run(check(directory, args.context))
            expected = all(result["apps"][app]["state"] == "collector-passed" for app in LAB_APPS if app != "seerr")
            if expected:
                break
            time.sleep(3)
        assert expected and result["media_sentinel_preserved"], "Real API/restart checks failed"
        print(json.dumps({"passed": True, "scope": result["scope"], "report": str(directory / "api-report.json")}))
    finally:
        # No volumes, images, other projects, or media are deleted.
        subprocess.run([*command, "down"], check=True, timeout=120)


if __name__ == "__main__":
    main()
