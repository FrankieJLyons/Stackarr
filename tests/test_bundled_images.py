import copy
import json

import pytest

from stackarr.bundled_images import catalog, verify
from stackarr.deployment import DeploymentError, images
from stackarr.updates import catalog as updates_catalog
from stackarr.updates import version_order


def test_security_image_catalogs_agree_and_update_is_newer():
    row = catalog()["seerr"]
    assert row["image"] == images()["seerr"] == updates_catalog()["apps"]["seerr"]["image"]
    assert version_order("3.5.0") < version_order(row["version"]) < version_order("3.5.1")


@pytest.mark.parametrize("changed", ["missing", "digest", "architecture", "version", "patch", "setup_patch", "missing_setup_patch"])
def test_bundled_image_fails_closed_without_network_fallback(changed):
    row = catalog()["seerr"]
    info = {"RepoDigests": [row["image"]], "Os": "linux", "Architecture": "amd64", "Config": {"Labels": {
        "org.opencontainers.image.version": row["version"], "io.stackarr.seerr.security-patch": row["patch"],
        "io.stackarr.seerr.setup-patch": row["setup_patch"]}}}
    assert verify(lambda args: json.dumps([info]), row["image"])
    wrong = copy.deepcopy(info)
    if changed == "digest":
        wrong["RepoDigests"] = []
    elif changed == "architecture":
        wrong["Architecture"] = "arm64"
    elif changed in {"version", "patch"}:
        wrong["Config"]["Labels"]["org.opencontainers.image.version" if changed == "version" else "io.stackarr.seerr.security-patch"] = "unreviewed"
    elif changed == "setup_patch":
        wrong["Config"]["Labels"]["io.stackarr.seerr.setup-patch"] = "unreviewed"
    elif changed == "missing_setup_patch":
        wrong["Config"]["Labels"].pop("io.stackarr.seerr.setup-patch")
    calls = []
    def inspect(args):
        calls.append(args)
        if changed == "missing":
            raise RuntimeError("missing")
        return json.dumps([wrong])
    with pytest.raises(DeploymentError, match="complete downloaded package"):
        verify(inspect, row["image"])
    assert calls == [["image", "inspect", row["image"]]]
    assert verify(inspect, "plexinc/pms-docker@sha256:" + "a" * 64) is False
