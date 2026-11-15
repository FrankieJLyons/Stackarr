"""Maintainer-only CLI relay: inject one real bind conflict in an isolated lab.

Frozen separately as docker.exe; never included in a Stackarr release. Only the
new lab controller inherits its PATH. All other commands relay unchanged.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    control = Path(os.environ["STACKARR_LAB_PROXY_CONFIG"]).resolve(strict=True)
    config = json.loads(control.read_text())
    root = Path(config["root"]).resolve(strict=True)
    assert control.is_relative_to(root) and root.name == "docker-startup-ports-20261018-r1"
    docker, args = config["docker"], sys.argv[1:]
    def call(arguments):
        result = subprocess.run([docker, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        assert result.returncode == 0, "Isolated fault fixture failed; private Docker output withheld"
        return result.stdout.strip()
    if config["mode"] == "armed" and "compose" in args and "up" in args and "-f" in args:
        filename = Path(args[args.index("-f") + 1]).resolve(strict=True)
        deployment_root = Path(config["deployment_root"]).resolve()
        assert deployment_root.is_relative_to(root) and deployment_root.name == "deployments"
        if filename.is_relative_to(deployment_root):
            identity = filename.parent.name
            project = "stackarr-owned-" + identity
            assert len(identity) == 32 and all(c in "0123456789abcdef" for c in identity)
            assert args[args.index("--project-name") + 1] == project
            recipe = json.loads(filename.read_text())
            assert set(recipe["services"]) == {"prowlarr", "qbittorrent"}
            config["mode"] = "spent"
            control.write_text(json.dumps(config))
            base = args[:args.index("up")]
            call([*base, "create", "--pull", "never"])
            call([*base, "start", "prowlarr"])
            prowlarr = json.loads(call(["inspect", project + "-prowlarr-1"]))[0]
            port = recipe["services"]["prowlarr"]["ports"][0]["published"]
            for _ in range(90):
                try:
                    token = ET.fromstring(call(["exec", prowlarr["Id"], "cat", "/config/config.xml"])).findtext("ApiKey")
                    url = "http://127.0.0.1:" + str(port) + "/api/v1/config/ui"
                    request = urllib.request.Request(url, headers={"X-Api-Key": token})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        ui = json.load(response)
                    ui["enableColorImpairedMode"] = True
                    request = urllib.request.Request(url + "/1", data=json.dumps(ui).encode(), method="PUT",
                        headers={"X-Api-Key": token, "Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=5) as response:
                        assert response.status == 202 or response.status == 200
                    break
                except Exception:
                    time.sleep(.5)
            else:
                raise AssertionError("The new lab Prowlarr did not become ready")
            volume = project + "_qbittorrent-config"
            call(["run", "--rm", "--user", "0:0", "--network", "none", "--label", "io.stackarr.lab=" + config["label"],
                "--mount", "type=volume,source=" + volume + ",target=/config", "--entrypoint", "python", config["helper"], "-c",
                "from pathlib import Path;p=Path('/config/stackarr-startup-port-sentinel.txt');p.write_text('original partial-install settings');p.chmod(0o666)"])
            blocked = int(recipe["services"]["qbittorrent"]["ports"][0]["published"])
            owner = call(["run", "-d", "--name", config["owner_name"], "--label", "io.stackarr.lab=" + config["label"],
                "--network", "bridge", "--publish", "127.0.0.1:" + str(blocked) + ":5055", "--memory", "128m", "--pids-limit", "64",
                "--entrypoint", "python", config["helper"], "-c", "from http.server import HTTPServer,SimpleHTTPRequestHandler;HTTPServer(('0.0.0.0',5055),SimpleHTTPRequestHandler).serve_forever()"])
            (root / "packaged-fault.json").write_text(json.dumps({"id": identity, "prowlarr": prowlarr["Id"],
                "qbittorrent": json.loads(call(["inspect", project + "-qbittorrent-1"]))[0]["Id"],
                "port": blocked, "owner": owner, "volume": volume}))
    result = subprocess.run([docker, *args])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
