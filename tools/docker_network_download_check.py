"""Real engine/download faults confined to a nested daemon and original fixtures."""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from stackarr import onboarding
from stackarr.deployment import DeploymentError, Deployments, images
from stackarr.docker_runtime import executable
from stackarr.self_update import read, write
from stackarr.store import Store
from tools import docker_app_maintenance_check as preservation
from tools.download_registry_fixture import build

ROOT = Path("test-results/docker-network-download-20261018-r2").resolve()
ENGINE = "stackarr-network-download-engine-20261018-r2"
REGISTRY = "stackarr-network-download-registry-20261018-r2"
LABEL = "network-download-20261018-r2"
REGISTRY_ROOT = ROOT / "registry"
CALLS = []
RACE = False


def outer(args, check=True, **kwargs):
    result = subprocess.run([executable(), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=kwargs.pop("timeout", 60), creationflags=subprocess.CREATE_NO_WINDOW, **kwargs)
    if check:
        assert result.returncode == 0, "An isolated lab Docker command failed."
    return result


def inner(args, check=True):
    return outer(["exec", ENGINE, "docker", *args], check=check)


def runner(args, **kwargs):
    global RACE
    remaining = args[1:]
    CALLS.append(remaining)
    if remaining[0] == "context":
        return subprocess.run(args, **kwargs)
    assert remaining[:2] == ["--context", "desktop-linux"]
    remaining = remaining[2:]
    if remaining[0] == "compose":
        index = remaining.index("-f") + 1
        filename = Path(remaining[index])
        assert filename.resolve().is_relative_to(ROOT) and filename.name == "compose.json"
        identity = filename.parent.name
        assert len(identity) == 32 and all(c in "0123456789abcdef" for c in identity)
        directory = "/lab/" + identity
        outer(["exec", ENGINE, "mkdir", "-p", directory])
        outer(["cp", str(filename), ENGINE + ":" + directory + "/compose.json"])
        remaining = remaining.copy()
        remaining[index] = directory + "/compose.json"
        if "up" in remaining and RACE:
            RACE = False
            inner(["network", "create", "--label", "io.stackarr.lab=" + LABEL, "capacity-two"])
        if "pull" in remaining:
            # Record this exact CLI inside the nested daemon for a genuine kill.
            return subprocess.run([executable(), "exec", ENGINE, "sh", "-c",
                'echo $$ > "$1"; shift; exec docker "$@"', "sh", directory + "/pull.pid", *remaining], **kwargs)
    return subprocess.run([executable(), "exec", ENGINE, "docker", *remaining], **kwargs)


def control(mode="healthy", layer=None):
    write(REGISTRY_ROOT / "control.json", {"mode": mode, "layer": layer})


def service(case):
    assert case in {"capacity", "late-network", "cut", "denied", "killed"}
    value = Deployments(Store(ROOT / ("state-" + case)), runner=runner)
    onboarding.initialize(value.store)
    return value


def review(value, image, port=43500):
    draft = onboarding.read(value.store)
    onboarding.save(value.store, onboarding.SaveDraft(revision=draft["revision"], draft=onboarding.SetupDraft(
        apps=["seerr"], choices={"seerr": {"mode": "install", "port": port}})))
    # Only this maintainer process replaces the image lock with a pinned original
    # fixture. Production packages have no test flags or alternative registries.
    with patch("stackarr.deployment.images", return_value={"seerr": image}):
        return value.review()


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()
    if (ROOT / "sentinel.json").exists():
        before = read(ROOT / "sentinel.json")
        info = json.loads(inner(["inspect", "original-settings-sentinel"]).stdout)[0]
        assert info["Id"] == before["id"] and info["State"]["Running"]
        assert inner(["exec", "original-settings-sentinel", "/bin/busybox", "cat", "/app/config/preserve.txt"]).stdout.strip() == "original-settings"


def record(case, **proof):
    preserved()
    file = ROOT / "cases.json"
    report = read(file) if file.exists() else {"cases": []}
    assert case not in {row["case"] for row in report["cases"]}
    report["cases"].append({"case": case, "passed": True, "main_preserved": True, **proof})
    write(file, report)
    print("Isolated Docker acceptance passed: " + case, flush=True)


def resources(identity):
    project = "stackarr-owned-" + identity
    return {"containers": inner(["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]).stdout.split(),
            "volumes": inner(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project]).stdout.split()}


def complete(value, identity, image):
    row = value.rows()[0]
    assert row["id"] == identity and row["state"] == "needs-setup" and row["phase"] == "complete", row["message"]
    info = json.loads(inner(["inspect", "stackarr-owned-" + identity + "-seerr-1"]).stdout)[0]
    assert info["State"]["Running"] and info["Config"]["Image"] == image
    with value.store.db() as db:
        assert db.execute("SELECT count(*) FROM deployments").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit WHERE event='deployment.started'").fetchone()[0] == 1
    assert inner(["exec", info["Id"], "/bin/busybox", "cat", "/app/config/preserve.txt"]).stdout.strip() == "original-settings"
    inner(["compose", "--project-name", "stackarr-owned-" + identity, "-f", "/lab/" + identity + "/compose.json", "down"])
    return info["Id"]


def prepare():
    assert ROOT.is_relative_to(Path.cwd()) and (ROOT / "main-before.json").exists()
    REGISTRY_ROOT.mkdir(exist_ok=True)
    binaries = ROOT / "binaries"
    binaries.mkdir(exist_ok=True)
    outer(["cp", ENGINE + ":/bin/busybox", str(binaries / "busybox")])
    outer(["cp", ENGINE + ":/lib/ld-musl-x86_64.so.1", str(binaries / "musl")])
    fixtures = {key: build(REGISTRY_ROOT, binaries, key) for key in ("sentinel", "capacity", "late-network", "cut", "denied", "killed")}
    write(ROOT / "fixtures.json", fixtures)
    shutil.copyfile(Path(__file__).with_name("download_registry_fixture.py"), REGISTRY_ROOT / "registry.py")
    control()
    outer(["run", "-d", "--name", REGISTRY, "--label", "io.stackarr.lab=" + LABEL,
        "--network", "container:" + ENGINE, "--memory", "256m", "--pids-limit", "128",
        "--mount", "type=bind,source=" + str(REGISTRY_ROOT) + ",target=/fixture",
        "--entrypoint", "python", "sha256:1f42e159fdb9c33f935deb3d56517f4cb2c9dd21f598d88c1bb098296b63a4d2", "/fixture/registry.py"])
    for _ in range(60):
        if (REGISTRY_ROOT / "observations.json").exists():
            break
        time.sleep(.5)
    assert (REGISTRY_ROOT / "observations.json").exists()
    image = fixtures["sentinel"]["image"]
    inner(["pull", image])
    identifier = inner(["run", "-d", "--name", "original-settings-sentinel", "--network", "bridge",
                        "--mount", "type=volume,source=original-settings-sentinel,target=/app/config", image]).stdout.strip()
    write(ROOT / "sentinel.json", {"id": identifier})
    preserved()
    print("Separate two-slot Docker engine and original local registry fixtures ready.", flush=True)


def capacity():
    fixtures = read(ROOT / "fixtures.json")
    for name in ("capacity-one", "capacity-two"):
        inner(["network", "create", "--label", "io.stackarr.lab=" + LABEL, name])
    value = service("capacity")
    context = value.context()
    before = inner(["network", "ls", "-q", "--no-trunc"]).stdout
    observed = value.network_capacity(context)
    assert observed["state"] == "exhausted" and observed["estimated_free"] == 0
    assert before == inner(["network", "ls", "-q", "--no-trunc"]).stdout
    try:
        value._call(["--context", context["name"], "network", "create", "proof-exhausted"])
    except DeploymentError as error:
        assert error.kind == "network-capacity"
    else:
        raise AssertionError("Actual nested engine exhaustion did not occur")
    try:
        review(value, fixtures["capacity"]["image"])
    except DeploymentError as error:
        assert error.kind == "network-capacity"
    else:
        raise AssertionError("Exhausted capacity must block review")
    assert not value.rows()
    record("actual-two-slot-network-exhaustion-and-read-only-diagnostics", actual_engine_exhaustion=True)
    inner(["network", "rm", "capacity-two"])
    payload = review(value, fixtures["capacity"]["image"])
    identity = value.enqueue(payload)
    inner(["network", "create", "--label", "io.stackarr.lab=" + LABEL, "capacity-two"])
    asyncio.run(value.run_one())
    assert value.rows()[0]["diagnostic"] == "network-capacity" and not any(resources(identity).values())
    inner(["network", "rm", "capacity-two"])
    value.resume(identity)
    asyncio.run(value.run_one())
    complete(value, identity, fixtures["capacity"]["image"])
    record("capacity-change-after-review-and-same-installation-resume", no_app_resources_before_resume=True)


def late_network():
    global RACE
    fixture = read(ROOT / "fixtures.json")["late-network"]
    value = service("late-network")
    if value.rows():
        identity = value.rows()[0]["id"]
        assert value.rows()[0]["state"] == "failed"
    else:
        identity = value.enqueue(review(value, fixture["image"], 43501))
        RACE = True
        asyncio.run(value.run_one())
    assert not RACE and value.rows()[0]["diagnostic"] == "network-capacity"
    retained = resources(identity)
    assert not retained["containers"]
    assert all(name == "stackarr-owned-" + identity + "_seerr-config" for name in retained["volumes"])
    inner(["network", "rm", "capacity-two"])
    before = read(REGISTRY_ROOT / "observations.json")["requests"]
    control("unauthorized")
    value.resume(identity)
    asyncio.run(value.run_one())
    complete(value, identity, fixture["image"])
    assert before == read(REGISTRY_ROOT / "observations.json")["requests"]
    control()
    record("actual-final-start-network-race-and-offline-cache-resume", no_registry_requests_on_resume=True,
           partially_created_owned_settings_volume_retained=bool(retained["volumes"]))


def cut():
    fixture = read(ROOT / "fixtures.json")["cut"]
    value = service("cut")
    identity = value.enqueue(review(value, fixture["image"], 43502))
    before = read(REGISTRY_ROOT / "observations.json")
    control("cut-once", fixture["layer"])
    asyncio.run(value.run_one())
    complete(value, identity, fixture["image"])
    after = read(REGISTRY_ROOT / "observations.json")
    assert after["cuts"] > before["cuts"] and after["partial_bytes"] >= before["partial_bytes"] + 262144
    record("real-partial-blob-disconnection-and-digest-verified-retry", actual_partial_bytes=262144)


def denied():
    fixture = read(ROOT / "fixtures.json")["denied"]
    value = service("denied")
    identity = value.enqueue(review(value, fixture["image"], 43503))
    control("unauthorized")
    CALLS.clear()
    asyncio.run(value.run_one())
    assert value.rows()[0]["state"] == "failed" and value.rows()[0]["diagnostic"] == "download-unavailable"
    assert len([args for args in CALLS if "pull" in args]) == 1 and not any(resources(identity).values())
    control()
    current, settings = value.store.config()
    settings.dashboard.appearance = "light"
    value.store.save(settings, current)
    value.resume(identity)
    asyncio.run(value.run_one())
    complete(value, identity, fixture["image"])
    assert value.store.config()[1].dashboard.appearance == "light"
    record("actual-registry-access-failure-and-explicit-download-retry", single_failed_pull=True, unrelated_settings_preserved=True)


def worker(resuming=False):
    fixture = read(ROOT / "fixtures.json")["killed"]
    value = service("killed")
    if resuming:
        identity = read(ROOT / "killed-operation.json")["id"]
        assert value.rows()[0]["state"] == "interrupted" and value.rows()[0]["phase"] == "downloading"
        value.resume(identity)
    else:
        identity = value.enqueue(review(value, fixture["image"], 43504))
        write(ROOT / "killed-operation.json", {"id": identity})
    asyncio.run(value.run_one())


def killed():
    fixture = read(ROOT / "fixtures.json")["killed"]
    control("hold", fixture["layer"])
    before = read(REGISTRY_ROOT / "observations.json")["held_bytes"]
    child = subprocess.Popen([sys.executable, "-m", "tools.docker_network_download_check", "worker"], creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(180):
        assert child.poll() is None, "Download worker exited before partial transfer"
        if read(REGISTRY_ROOT / "observations.json")["held_bytes"] > before:
            break
        time.sleep(.5)
    else:
        raise AssertionError("Actual partial blob transfer was not observed")
    identity = read(ROOT / "killed-operation.json")["id"]
    assert not any(resources(identity).values())
    child.kill()
    child.wait(timeout=30)
    pid = outer(["exec", ENGINE, "cat", "/lab/" + identity + "/pull.pid"]).stdout.strip()
    assert pid.isdecimal() and int(pid) > 1
    outer(["exec", ENGINE, "kill", "-TERM", pid])
    value = service("killed")
    assert value.rows()[0]["state"] == "interrupted" and value.rows()[0]["phase"] == "downloading"
    assert not asyncio.run(value.run_one()) and not any(resources(identity).values())
    control()
    result = subprocess.run([sys.executable, "-m", "tools.docker_network_download_check", "retry-worker"], timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0
    complete(service("killed"), identity, fixture["image"])
    record("actual-worker-and-download-cli-exit-with-fresh-process-resume", actual_partial_bytes=262144,
           no_automatic_app_writes=True, same_deployment_and_single_activation=True)


def catalog():
    # Inspect cached real catalog images only; never pull, start or change apps.
    value = Deployments(Store(ROOT / "catalog-verification"))
    context = value.context()
    verified = {}
    for key, image in images().items():
        value._verify_images({"context": context, "compose": {"services": {key: {"image": image}}}})
        verified[key] = True
    assert len(verified) == 9
    write(ROOT / "catalog-image-verification.json", verified)
    print("All nine real cached catalog image digests/platforms verified read-only.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "capacity", "late-network", "cut", "denied", "killed", "worker", "retry-worker", "catalog"))
    argument = parser.parse_args().phase
    if argument in {"worker", "retry-worker"}:
        worker(argument == "retry-worker")
    else:
        globals()[argument.replace("-", "_")]()
