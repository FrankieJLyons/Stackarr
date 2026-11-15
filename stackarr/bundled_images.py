"""Verify security-patched app images delivered inside the complete preview tar."""

import json
import re
from pathlib import Path

from .deployment import DeploymentError


def catalog():
    rows = json.loads(Path(__file__).with_name("bundled-images.lock.json").read_text(encoding="utf-8"))
    if (set(rows) != {"seerr"} or not re.fullmatch(r"stackarr-seerr@sha256:[a-f0-9]{64}", rows["seerr"]["image"])
            or rows["seerr"]["version"] != "3.5.0-stackarr.2" or rows["seerr"]["patch"] != "manage-users-1"
            or rows["seerr"].get("setup_patch") != "plex-setup-1"):
        raise DeploymentError("The packaged app image catalog is invalid.")
    return rows


def verify(call, reference):
    row = next((row for row in catalog().values() if row["image"] == reference), None)
    if row is None:
        return False
    try:
        info = json.loads(call(["image", "inspect", reference]))[0]
        labels = info["Config"]["Labels"]
        assert (reference in info["RepoDigests"] and info["Os"] == "linux" and info["Architecture"] == "amd64"
                and labels["org.opencontainers.image.version"] == row["version"]
                and labels["io.stackarr.seerr.security-patch"] == row["patch"]
                and labels["io.stackarr.seerr.setup-patch"] == row["setup_patch"])
    except Exception:
        raise DeploymentError("The packaged Seerr security image is missing or changed. Reopen Start Stackarr from the complete downloaded package, then retry; existing app data is retained.", kind="download-verification") from None
    return True
