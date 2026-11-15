"""Real final-start port races confined to new owned Docker installations."""

import argparse
import asyncio
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import patch

import httpx

from stackarr import onboarding
from stackarr.arr_logins import prepare, verified_login
from stackarr.arr_logins import read as app_login
from stackarr.bootstrap import accepted, credentials
from stackarr.deployment import Deployments
from stackarr.install_ports import InstallPorts
from stackarr.self_update import read, write
from stackarr.store import Conflict, Store
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import command, hashes

ROOT = Path("test-results/docker-startup-ports-20261018-r1").resolve()
LABEL = "startup-ports-20261018-r1"
HELPER = "sha256:9c759d0a9a0b7175cc1fd0efeced39a8963173aba643f38b9551fcc79a4df30f"
MARKER = "original partial-install settings"
CASES = {"available", "freed", "stolen", "interrupted", "repeated", "shared"}


def receipt(service, identity):
    with service.store.db() as db:
        return json.loads(db.execute("SELECT payload FROM deployments WHERE id=?", (identity,)).fetchone()[0])


def info(identity, key):
    return json.loads(command(["inspect", "stackarr-owned-" + identity + "-" + key + "-1"]))[0]


def owner(name, port):
    # This responder owns only a lab port and the built-in bridge. No host mounts.
    script = "from http.server import BaseHTTPRequestHandler,HTTPServer\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(b'Original startup-port owner')\n def log_message(self,*a): pass\nHTTPServer(('0.0.0.0',5055),H).serve_forever()"
    return command(["run", "-d", "--name", name, "--label", "io.stackarr.lab=" + LABEL,
        "--network", "bridge", "--publish", "127.0.0.1:" + str(port) + ":5055", "--memory", "128m",
        "--pids-limit", "64", "--entrypoint", "python", HELPER, "-c", script])


def remove_owner(identifier):
    observed = json.loads(command(["inspect", identifier]))[0]
    assert observed["Config"]["Labels"].get("io.stackarr.lab") == LABEL
    command(["rm", "--force", identifier])


def marker(identity, *, create=False):
    volume = "stackarr-owned-" + identity + "_qbittorrent-config"
    script = "from pathlib import Path;p=Path('/config/stackarr-startup-port-sentinel.txt');"
    script += "p.write_text(" + repr(MARKER) + ");p.chmod(0o666)" if create else "print(p.read_text())"
    result = command(["run", "--rm", "--user", "0:0", "--label", "io.stackarr.lab=" + LABEL, "--network", "none", "--entrypoint", "python",
        "--mount", "type=volume,source=" + volume + ",target=/config" + ("" if create else ",readonly"), HELPER, "-c", script])
    if not create:
        assert result == MARKER


def seed_prowlarr(service, identity, payload):
    partial = copy.deepcopy(payload)
    partial["apps"] = ["prowlarr"]
    saved = credentials(service, identity, partial)
    prepare(service, identity, partial, saved)
    port = payload["config"]["integrations"]["prowlarr"]["port"]
    with httpx.Client(base_url="http://127.0.0.1:" + str(port), trust_env=False,
                      headers={"X-Api-Key": saved["prowlarr"]["api_key"]}, timeout=20) as client:
        for _ in range(60):
            try:
                resource = client.get("/api/v1/config/ui").json()
                resource["enableColorImpairedMode"] = True
                client.put("/api/v1/config/ui/1", json=resource).raise_for_status()
                break
            except (httpx.HTTPError, ValueError):
                time.sleep(.5)
        else:
            raise AssertionError("The isolated Prowlarr setting was not ready")
    return saved["prowlarr"]["api_key"]


def verify(service, identity, before, owners=()):
    payload = receipt(service, identity)
    row = service.rows()[0]
    assert row["state"] == "needs-setup" and row["phase"] == "complete", row["message"]
    assert info(identity, "prowlarr")["Id"] == before["prowlarr"]
    assert info(identity, "qbittorrent")["State"]["Running"]
    observed = InstallPorts(service).inspect(identity, payload)
    assert {key: row["resources"] for key, row in observed.items()} == before["resources"]
    marker(identity)
    token = service.store.secret("prowlarr")["api_key"]
    assert hashlib.sha256(token.encode()).hexdigest() == before["api_key"]
    login = app_login(service, identity, payload, "prowlarr", token)
    assert hashlib.sha256(json.dumps(login, sort_keys=True).encode()).hexdigest() == before["login"]
    config = service.store.config()[1]
    with httpx.Client(base_url=config.integrations["prowlarr"].url, trust_env=False, headers={"X-Api-Key": token}, timeout=20) as client:
        assert client.get("/api/v1/config/ui").json()["enableColorImpairedMode"] is True
    address = config.integrations["qbittorrent"].url
    with httpx.Client(base_url=address, trust_env=False, headers={"Referer": address}, timeout=20) as client:
        assert accepted(client.post("/api/v2/auth/login", data=service.store.secret("qbittorrent")))
        assert client.get("/api/v2/torrents/info").json() == []
    with service.store.db() as db:
        assert db.execute("SELECT count(*) FROM deployments").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit WHERE event='deployment.started'").fetchone()[0] == 1
    assert hashes(ROOT / "media") == read(ROOT / "media-before.json")
    for identifier in owners:
        assert json.loads(command(["inspect", identifier]))[0]["State"]["Running"]
    preservation.OUTPUT = ROOT
    preservation.main_preserved()


def record(case, **proof):
    report = read(ROOT / "cases.json") if (ROOT / "cases.json").exists() else {"cases": []}
    assert case not in {row["case"] for row in report["cases"]}
    report["cases"].append({"case": case, "passed": True, "main_preserved": True, **proof})
    write(ROOT / "cases.json", report)
    print("Isolated final-start acceptance passed: " + case, flush=True)


def native(case):
    assert case in CASES
    directory = ROOT / case
    directory.mkdir()
    state = directory / "state"
    owners = []
    injected = [False]
    service = Deployments(Store(state), auto_logins=True)
    onboarding.initialize(service.store)
    draft = onboarding.read(service.store)
    onboarding.save(service.store, onboarding.SaveDraft(revision=draft["revision"], draft=onboarding.SetupDraft(
        apps=["prowlarr", "qbittorrent"], data_root=str(ROOT / "media"), port_mode="custom",
        choices={"prowlarr": {"mode": "install", "port": 43600}, "qbittorrent": {"mode": "install", "port": 43601}})))
    payload = service.review()
    identity = service.enqueue(payload)
    write(directory / "operation.json", {"id": identity})
    def runner(args, **kwargs):
        if "compose" in args and "up" in args and not injected[0]:
            injected[0] = True
            try:
                base = args[1:args.index("up")]
                assert Path(base[base.index("-f") + 1]).resolve().is_relative_to(directory)
                command([*base, "create", "--pull", "never"])
                command([*base, "start", "prowlarr"])
                seed_prowlarr(service, identity, payload)
                marker(identity, create=True)
                owners.append(owner("stackarr-startup-" + case + "-original", 43601))
                write(directory / "owners.json", owners)
            except Exception:
                (directory / "harness-error.log").write_text(traceback.format_exc())
                raise
        return subprocess.run(args, **kwargs)
    service.runner = runner
    asyncio.run(service.run_one())
    row = service.rows()[0]
    assert row["state"] == "failed" and row["diagnostic"] == "startup-port-conflict", row["message"]
    assert info(identity, "prowlarr")["State"]["Running"] and not info(identity, "qbittorrent")["State"]["Running"]
    payload = receipt(service, identity)
    observed = InstallPorts(service).inspect(identity, payload)
    # Read through the protected normal handoff rather than print any credentials.
    with service.store.db() as db:
        saved = json.loads(service.store.cipher.decrypt(db.execute("SELECT value FROM deployment_secrets WHERE id=?", (identity,)).fetchone()[0]))
    token = saved["prowlarr"]["api_key"]
    login = app_login(service, identity, payload, "prowlarr", token)
    assert verified_login("http://127.0.0.1:43600", login)
    before = {"prowlarr": info(identity, "prowlarr")["Id"], "qbittorrent": info(identity, "qbittorrent")["Id"],
        "resources": {key: row["resources"] for key, row in observed.items()}, "api_key": hashlib.sha256(token.encode()).hexdigest(),
        "login": hashlib.sha256(json.dumps(login, sort_keys=True).encode()).hexdigest()}
    write(directory / "before.json", before)
    service.runner = subprocess.run
    helper = InstallPorts(service)
    if case == "freed":
        remove_owner(owners.pop())
        try:
            helper.review(identity)
        except Conflict as exc:
            assert "Resume installation" in str(exc)
        else:
            raise AssertionError("The original available address should be retained")
        service.resume(identity)
    else:
        if case == "shared":
            shared = command(["run", "-d", "--label", "io.stackarr.lab=" + LABEL, "--network", "none", "--entrypoint", "python",
                "--mount", "type=volume,source=stackarr-owned-" + identity + "_qbittorrent-config,target=/config,readonly", HELPER, "-c", "import time;time.sleep(600)"])
            try:
                helper.review(identity)
            except ValueError as exc:
                assert "shared" in str(exc)
            else:
                raise AssertionError("Shared settings must block recovery")
            remove_owner(shared)
        reviewed = helper.review(identity)
        if case == "stolen":
            owners.append(owner("stackarr-startup-stolen-proposed", reviewed["ports"]["qbittorrent"]))
            try:
                helper.approve(reviewed)
            except Conflict as exc:
                assert "became busy" in str(exc)
            else:
                raise AssertionError("A newly occupied proposed address must cancel approval")
            assert receipt(service, identity) == payload
            assert info(identity, "qbittorrent")["Id"] == before["qbittorrent"]
            reviewed = helper.review(identity)
        helper.approve(reviewed)
        if case == "interrupted":
            result = subprocess.run([sys.executable, "-m", "tools.docker_startup_ports_check", "interrupt"], timeout=90)
            assert result.returncode == 77
            service = Deployments(Store(state), auto_logins=True)
            assert service.rows()[0]["state"] == "interrupted"
            assert info(identity, "qbittorrent")["Id"] == before["qbittorrent"]
            service.resume(identity)
        if case == "repeated":
            def repeat(args, **kwargs):
                if "compose" in args and "up" in args:
                    owners.append(owner("stackarr-startup-repeated-target", reviewed["ports"]["qbittorrent"]))
                    service.runner = subprocess.run
                return subprocess.run(args, **kwargs)
            service.runner = repeat
            asyncio.run(service.run_one())
            assert service.rows()[0]["diagnostic"] == "startup-port-conflict"
            assert info(identity, "qbittorrent")["Id"] != before["qbittorrent"]
            InstallPorts(service).approve(InstallPorts(service).review(identity))
    asyncio.run(service.run_one())
    verify(service, identity, before, owners)
    if case == "freed":
        assert info(identity, "qbittorrent")["Id"] != before["qbittorrent"]
        assert service.store.config()[1].integrations["qbittorrent"].port == 43601
    else:
        assert service.store.config()[1].integrations["qbittorrent"].port != 43601
    record("native-" + case, same_installation=identity, running_app_id_retained=True, settings_volume_retained=True,
           generated_login_retained=True, media_files=len(read(ROOT / "media-before.json")))
    for identifier in owners:
        remove_owner(identifier)
    command(["compose", "--project-name", "stackarr-owned-" + identity, "-f", str(state / "deployments" / identity / "compose.json"), "down"])


def interrupt():
    state = ROOT / "interrupted/state"
    service = Deployments(Store(state), auto_logins=True)
    original = InstallPorts.reconcile
    def exit_after_receipt(self, identity, payload, filename):
        original(self, identity, payload, filename)
        os._exit(77)
    with patch.object(InstallPorts, "reconcile", exit_after_receipt):
        asyncio.run(service.run_one())


def initialize():
    assert ROOT.is_relative_to(Path.cwd()) and not ROOT.exists()
    ROOT.mkdir()
    preservation.OUTPUT = ROOT
    write(ROOT / "main-before.json", preservation.main_snapshot())
    write(ROOT / "volumes-before.json", command(["volume", "ls", "-q"]).split())
    shutil.copytree(Path("test-results/docker-optional-maintenance-20261018/media"), ROOT / "media")
    write(ROOT / "media-before.json", hashes(ROOT / "media"))
    print("Isolated final-start lab prepared; main baseline captured.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["initialize", "interrupt", *sorted(CASES)])
    args = parser.parse_args()
    if args.action == "initialize":
        initialize()
    elif args.action == "interrupt":
        interrupt()
    else:
        native(args.action)
