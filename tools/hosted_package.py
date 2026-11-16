"""Build and smoke-test complete packages exclusively on disposable hosted Linux.

Windows assembly can validate the resulting image receipt without running Docker.
The existing Seerr dependency is recovered from the checksummed public release;
the dashboard and launcher are built from the current source revision.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from stackarr import __version__
from stackarr.bundled_images import catalog, verify
from stackarr.self_update import FILES, package


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def revision():
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("Hosted packaging requires a clean source checkout.")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def hosted():
    if (platform.system() != "Linux" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("Docker build/load/smoke commands require disposable GitHub-hosted Linux.")


def docker(args):
    hosted()
    return subprocess.check_output(["docker", *args], text=True, timeout=900).strip()


def inspect(image):
    return json.loads(docker(["image", "inspect", image]))[0]


def image_name():
    return "stackarr:" + __version__


def extract(archive, destination, *, images_only=False):
    """Only admit the exact flat package format, never ZIP-directed filesystem paths."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        paths = [PurePosixPath(info.filename) for info in infos]
        if (len(infos) != len(FILES) + 1 or len({p.parts[0] for p in paths if p.parts}) != 1
                or any(len(p.parts) != 2 or ".." in p.parts or "\\" in i.filename
                       or i.filename != str(p) or i.is_dir()
                       or (i.external_attr >> 16) & 0o170000 == 0o120000
                       for p, i in zip(paths, infos, strict=True))
                or {p.name for p in paths} != FILES | {"manifest.json"}):
            raise ValueError("Expected exactly the flat complete-package payload; unsafe or extra ZIP entries rejected.")
        for info, path in zip(infos, paths, strict=True):
            if images_only and path.name not in {"manifest.json", "stackarr-image.tar"}:
                continue
            with bundle.open(info) as source, (destination / path.name).open("xb") as target:
                shutil.copyfileobj(source, target)
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if digest(destination / "stackarr-image.tar") != manifest.get("files", {}).get("stackarr-image.tar"):
        raise ValueError("Image archive hash does not match the package manifest.")
    if not images_only:
        package(destination)
    return manifest


def validate_bundle(source, expected_revision, expected_image):
    """Validate hosted handoff on Windows without opening a Docker connection."""
    source = Path(source)
    receipt = json.loads((source / "image-build.json").read_text(encoding="utf-8"))
    rows = receipt.get("bundled_app_images", [])
    expected = {key: value["image"] for key, value in catalog().items()}
    if (receipt.get("schema") != 1 or receipt.get("source_revision") != expected_revision
            or receipt.get("source_dirty") is not False or receipt.get("version") != __version__
            or receipt.get("image") != expected_image or receipt.get("catalog") != catalog()
            or len(rows) != len(expected) or {row.get("app"): row.get("image") for row in rows} != expected
            or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", row.get("image_id", "")) for row in rows)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", receipt.get("image_id", ""))):
        raise ValueError("Image receipt does not match this clean revision, version or reviewed catalog.")
    if digest(source / "stackarr-image.tar") != receipt.get("archive_sha256"):
        raise ValueError("Hosted image archive changed after export.")
    return receipt


def validate_launcher(source, expected_revision):
    source = Path(source)
    receipt = json.loads((source / "build-metadata.json").read_text(encoding="utf-8"))
    if (receipt.get("source_revision") != expected_revision
            or receipt.get("artifacts_sha256", {}).get("StackarrPreview.exe") != digest(source / "StackarrPreview.exe")):
        raise ValueError("Launcher was not built from this revision or changed after its build.")


def build(output):
    hosted()
    source_revision = revision()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(Path("platform/docker/release-inputs.lock.json").read_text(encoding="utf-8"))
    baseline = output / "baseline.zip"
    with urllib.request.urlopen(lock["url"], timeout=120) as response, baseline.open("xb") as target:
        shutil.copyfileobj(response, target)
    if digest(baseline) != lock["sha256"]:
        raise ValueError("The public dependency release checksum changed.")
    previous = extract(baseline, output / "baseline", images_only=True)
    if {row["app"]: row["image"] for row in previous.get("bundled_app_images", [])} != {
            key: row["image"] for key, row in catalog().items()}:
        raise ValueError("The baseline release does not contain the reviewed Seerr dependency.")
    docker(["load", "--input", str(output / "baseline/stackarr-image.tar")])
    tags, rows = [], []
    for key, row in catalog().items():
        verify(docker, row["image"])
        info = inspect(row["image"])
        tag = row["image"].split("@", 1)[0] + ":" + row["version"]
        docker(["tag", row["image"], tag])
        tags.append(tag)
        rows.append({"app": key, "image": row["image"], "image_id": info["Id"]})
    docker(["pull", "--platform", "linux/amd64", "python:3.13-slim"])
    base = inspect("python:3.13-slim")["RepoDigests"][0]
    docker(["build", "--platform", "linux/amd64", "--build-arg", "STACKARR_BASE_IMAGE=" + base,
            "--label", "org.opencontainers.image.revision=" + source_revision,
            "--label", "org.opencontainers.image.version=" + __version__, "--tag", image_name(), "."])
    docker(["save", "--output", str(output / "stackarr-image.tar"), image_name(), *tags])
    write(output / "image-build.json", {
        "schema": 1, "version": __version__, "source_revision": source_revision, "source_dirty": False,
        "image": image_name(), "image_id": inspect(image_name())["Id"], "catalog": catalog(),
        "bundled_app_images": rows, "archive_sha256": digest(output / "stackarr-image.tar"),
        "dashboard_base": base, "dependency_release": lock,
        "limitations": ["Seerr is the unchanged pinned dependency from 0.1.0, not rebuilt in this run.",
                        "The resolved dashboard base is recorded; this is not a reproducible-build attestation."],
    })
    validate_bundle(output, source_revision, image_name())


def smoke(image, name, command, tmpfs):
    created = False
    try:
        docker(["run", "--detach", "--name", name, "--network", "none", "--pull", "never",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--tmpfs", tmpfs, image])
        created = True
        for _ in range(60):
            try:
                return json.loads(docker(["exec", name, *command]))
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                time.sleep(2)
        raise ValueError("Packaged service did not become healthy: " + name)
    finally:
        if created:
            docker(["rm", "--force", "--volumes", name])


def check(archive, bundle, output):
    hosted()
    source_revision = revision()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = extract(archive, output / "package")
    receipt = validate_bundle(bundle, source_revision, image_name())
    if (manifest.get("source_revision") != source_revision or manifest.get("source_dirty") is not False
            or manifest.get("signed") is not False or "alpha_test" in manifest
            or manifest.get("image") != receipt["image"] or manifest.get("image_id") != receipt["image_id"]
            or manifest.get("bundled_app_images") != receipt["bundled_app_images"]
            or manifest["files"]["stackarr-image.tar"] != receipt["archive_sha256"]):
        raise ValueError("Final package differs from the reviewed hosted image build.")
    docker(["load", "--input", str(output / "package/stackarr-image.tar")])
    info = inspect(manifest["image"])
    if (info["Id"] != manifest["image_id"] or info["Os"] != "linux" or info["Architecture"] != "amd64"
            or info["Config"]["Labels"].get("org.opencontainers.image.revision") != source_revision):
        raise ValueError("Dashboard identity or source label changed during export/import.")
    for row in manifest["bundled_app_images"]:
        verify(docker, row["image"])
        if inspect(row["image"])["Id"] != row["image_id"]:
            raise ValueError("Seerr identity changed during export/import.")
    health = smoke(manifest["image"], "stackarr-hosted-dashboard", ["python", "-c",
        "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8787/healthz', headers={'Host':'localhost:8787'})).read().decode())"],
        "/var/lib/stackarr:uid=10001,gid=10001,mode=0700")
    if health.get("status") != "ok":
        raise ValueError("Packaged dashboard health check failed.")
    seerr = smoke(catalog()["seerr"]["image"], "stackarr-hosted-seerr", ["node", "-e",
        "fetch('http://127.0.0.1:5055/api/v1/status').then(async r=>{if(!r.ok)throw Error(r.status);console.log(await r.text())}).catch(()=>process.exit(1))"],
        "/app/config:uid=1000,gid=1000,mode=0700")
    if seerr.get("version") != catalog()["seerr"]["version"]:
        raise ValueError("Unexpected running Seerr version.")
    write(output / "complete-package-check.json", {
        "passed": True, "source_revision": source_revision, "archive_sha256": digest(archive),
        "image_archive_sha256": receipt["archive_sha256"], "dashboard_health": health,
        "seerr_status": seerr, "exact_package_hashes_verified": True, "fresh_runner_image_load": True,
        "network": "none", "host_media_mounts": False,
        "limitations": ["Service smoke check; Windows Docker Desktop onboarding still needs a clean-host user test."],
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "check", "launcher"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--launcher", type=Path)
    args = parser.parse_args()
    if args.mode == "build":
        build(args.output)
    elif args.mode == "check":
        check(args.archive, args.bundle, args.output)
    else:
        validate_launcher(args.launcher, revision())


if __name__ == "__main__":
    main()
