"""Prepare an isolated, non-production Docker lab. Never starts or stops Docker."""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

from stackarr.config import CATALOG, Config
from stackarr.installer import compose_plan

LAB_APPS = ("plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr")
PORTS = {"stackarr": 28787, "plex": 32450, "sonarr": 28989, "radarr": 27878,
         "prowlarr": 29696, "qbittorrent": 28080, "seerr": 25055}


def locked_images():
    record = json.loads(Path(__file__).with_name("docker-lab-images.json").read_text())
    images = record["images"]
    if record["schema"] != 1 or set(images) != set(LAB_APPS):
        raise ValueError("Invalid lab image lock")
    for key, image in images.items():
        repository = CATALOG[key]["image"].rsplit(":", 1)[0]
        if not re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", image):
            raise ValueError("Lab images must use the catalog repository and immutable digests")
    return images


def lab_plan(directory, image, apps):
    """Use only a newly allocated test folder; never accept arbitrary media roots."""
    if not apps or len(set(apps)) != len(apps) or set(apps) - set(LAB_APPS):
        raise ValueError("Choose unique supported lab apps")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("Use the locally built Stackarr image ID, not a mutable tag")
    data = Config().model_dump()
    data["storage"]["data_root"] = str(directory / "media")
    for key in apps:
        data["integrations"][key].update(enabled=True, mode="install", port=PORTS[key])
    compose = compose_plan(Config.model_validate(data))["compose"]
    # Never attach this experiment to the normal/shared Stackarr control network.
    compose["networks"] = {"control": {}}
    images = locked_images()
    for key, service in compose["services"].items():
        service["image"] = images[key]
        service["platform"] = "linux/amd64"
        service.update(restart="no", cpus=1.0, mem_limit="768m")
        service["logging"] = {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}}
    compose["services"]["stackarr"] = {
        "image": image, "restart": "no", "init": True, "read_only": True,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "cpus": 1.0, "mem_limit": "256m",
        "ports": [{"target": 8787, "published": str(PORTS["stackarr"]), "host_ip": "127.0.0.1"}],
        "environment": {"STACKARR_ORIGIN": f"http://localhost:{PORTS['stackarr']}"},
        "volumes": [{"type": "volume", "source": "stackarr-data", "target": "/var/lib/stackarr"}],
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m"], "networks": ["control"],
    }
    compose["volumes"]["stackarr-data"] = {}
    return compose


def prepare(parent, image, apps):
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / ("stackarr-lab-" + uuid.uuid4().hex[:12])
    directory.mkdir()  # Exclusive allocation; never reuse someone else's state.
    compose = lab_plan(directory, image, apps)
    for child in ("media/movies", "media/tv", "downloads"):
        (directory / "media" / child).mkdir(parents=True, exist_ok=True)
    sentinel = directory / "media" / "preserve.txt"
    sentinel.write_text("Stackarr synthetic lab sentinel. Preserve across restart and stop.\n", encoding="utf-8")
    payload = json.dumps(compose, indent=2)
    (directory / "compose.json").write_text(payload, encoding="utf-8")
    receipt = {"schema": 1, "project": directory.name, "apps": apps,
               "ports": {key: PORTS[key] for key in ["stackarr", *apps]},
               "compose_sha256": hashlib.sha256(payload.encode()).hexdigest(),
               "sentinel_sha256": hashlib.sha256(sentinel.read_bytes()).hexdigest(),
               "scope": "Disposable local Docker lab; no playback or before-login certification",
               "upstream_images": {key: compose["services"][key]["image"] for key in apps}}
    (directory / "lab.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Local Stackarr image sha256 ID")
    parser.add_argument("--apps", nargs="+", choices=LAB_APPS, default=["plex", "sonarr", "qbittorrent", "seerr"])
    args = parser.parse_args()
    directory = prepare(Path("test-results/docker-lab"), args.image, args.apps)
    print(directory)
    print("Prepared only. Review compose.json, verify local Docker context and free ports before starting.")


if __name__ == "__main__":
    main()
