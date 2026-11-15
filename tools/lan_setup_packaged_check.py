"""Real packaged guided-LAN lifecycle on a new isolated loopback installation."""

import argparse
import base64
import json
import os
import secrets
import signal
import ssl
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from stackarr.lan_gateway import prepare
from stackarr.lan_setup import LanSetup
from stackarr.self_update import SelfUpdates, digest, read
from tools.lan_gateway_check import docker, free_port, job_done, run, snapshot, wait


def check(package, output, caddy):
    package, output, caddy = package.resolve(), output.resolve(), caddy.resolve()
    if output.exists() or not output.is_relative_to(Path("test-results").resolve()):
        raise ValueError("Choose a new directory under test-results.")
    output.mkdir(parents=True)
    before = snapshot()
    (output / "before-private.json").write_text(json.dumps(before))
    result = {"checks":{}, "physical_checks":"pending", "host_network_settings":"unchanged"}
    state, workspace = output / "state", output / "network"
    helper, client, log = None, None, None
    try:
        port, controller_port, gateway_port = free_port(), free_port(), free_port()
        assert len({port,controller_port,gateway_port}) == 3
        run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",package / "Start-StackarrPreview.ps1",
             "-StateDirectory",state,"-Port",port,"-ControllerPort",controller_port,"-NoBrowser"],timeout=300)
        installation = read(state / "installation.json")
        assert installation["project"] not in {row["project"] for row in before.values()}
        os.environ.update(STACKARR_PORT=str(installation["port"]), STACKARR_CONTROLLER_PORT=str(installation["controller_port"]))
        updates = SelfUpdates(state, package_root=package)
        active = updates.active()
        local_origin = f"http://localhost:{active['port']}"
        password = secrets.token_urlsafe(28)
        with httpx.Client(base_url=local_origin,trust_env=False,timeout=20) as local:
            token = docker("exec",active["project"],"cat","/var/lib/stackarr/setup-token")
            assert local.post("/api/setup",json={"password":password,"setup_token":token},headers={"Origin":local_origin}).status_code == 200
            assert local.post("/api/login",json={"password":password},headers={"Origin":local_origin}).status_code == 200
            config = local.get("/api/config").json()["config"]
            # Only the lab harness admits loopback; the novice form rejects it.
            setup = LanSetup(state,workspace,caddy,network_reader=lambda:[])
            identity = uuid.uuid4().hex
            remote = f"https://127.0.0.1:{gateway_port}"
            prepare(workspace / identity,{"origin":remote,"bind":"127.0.0.1","clients":["127.0.0.1/32"],"dashboard_port":active["port"],
                    "apps":{},"lab":True,"state_root":str(state)},caddy)
            setup.saved["bundle"] = identity
            setup.save()
            certificate, info = setup.certificate()
            context = ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(certificate))
            report = output / "window-private.json"
            log = (output / "helper.log").open("ab")
            command = [str(package / "StackarrPreview.exe"),"--lan-setup",str(state),"--lan-workspace",str(workspace),"--no-browser"]
            helper = subprocess.Popen([*command,"--lan-ready-report",str(report)],stdout=log,stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW,env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT":"1"})
            wait(lambda:report.exists(),60)
            url = read(report)["url"]
            parsed = urlsplit(url)
            origin = f"http://127.0.0.1:{parsed.port}"
            client = httpx.Client(base_url=origin,trust_env=False,timeout=120,headers={"Origin":origin,"X-LAN-Key":parsed.fragment})

            def action(name, data=None):
                response = client.post("/api/"+name,json=data or {})
                assert response.status_code == 200, (name,response.text)
                return response.json()

            assert action("status")["certificate"]["fingerprint"] == info["fingerprint"]
            assert "interfaces" in action("choices")  # Verifies pinned Caddy embedded in the frozen executable.
            assert base64.b64decode(action("certificate")["data"]) == certificate
            result["checks"]["frozen_assets_bundled_gateway_public_certificate"] = True
            second = output / "reopened-private.json"
            run([*command,"--lan-ready-report",second],timeout=60)
            assert read(second)["reused"] and read(second)["url"] == url
            result["checks"]["reopen_reuses_existing_helper_and_certificate"] = True
            review = action("review",{"action":"enable"})
            assert action("status")["job"] is None
            job = action("apply",{"token":review["token"]})["job"]
            assert client.post("/api/apply",json={"token":review["token"]}).status_code == 409
            outcome = job_done(updates,job["id"])
            assert outcome["phase"] == "succeeded", outcome.get("failure")
            assert local.get("/api/config").json()["config"] == config
            result["checks"]["reviewed_one_use_activation_preserves_local_session_settings"] = True
            assert action("start")["gateway_running"]
            with httpx.Client(base_url=remote,verify=context,trust_env=False,timeout=15) as remote_client:
                assert remote_client.get("/api/config").status_code == 401
                login = remote_client.post("/api/login",json={"password":password},headers={"Origin":remote})
                assert login.status_code == 200 and "Secure" in login.headers["set-cookie"]
                assert remote_client.get("/api/config").json()["config"] == config
                result["checks"]["guided_start_validates_tls_and_owner_login"] = True
                assert action("stop")["gateway_running"] is False
                try:
                    remote_client.get("/healthz")
                    raise AssertionError("The owned gateway did not stop")
                except httpx.ConnectError:
                    pass
                assert action("start")["gateway_running"]
                assert remote_client.get("/api/config").status_code == 200
                assert action("status")["certificate"]["fingerprint"] == info["fingerprint"]
                result["checks"]["stop_restart_keeps_certificate_and_authenticated_session"] = True
            undo = action("review",{"action":"undo"})
            job = action("apply",{"token":undo["token"]})["job"]
            outcome = job_done(updates,job["id"])
            assert outcome["phase"] == "rolled-back", outcome.get("failure")
            assert local.get("/api/config").json()["config"] == config
            assert local.get("/healthz",headers={"Host":urlsplit(remote).netloc}).status_code == 400
            assert client.post("/api/start",json={}).status_code == 409
            result["checks"]["guided_undo_revokes_lan_and_blocks_restart_until_review"] = True
            status = action("status")
            assert status["physical_status"] == "pending" and status["reboot_status"] == "not-certified"
            action("close")
            helper.wait(30)
            result["checks"]["close_stops_helper_retains_saved_setup_physical_checks_pending"] = True
        # Shutdown only this new fixture after validating its receipts and signed controller probe.
        active = updates.active()
        identity, container = updates.dashboard(active["port"])
        assert identity not in before and container["Config"]["Labels"]["com.docker.compose.project"] == installation["project"]
        probe = updates.controller_probe(active)
        release, _ = updates.release(active["release"])
        assert probe["executable"] == digest(release / "StackarrPreview.exe")
        docker("stop",identity)
        os.kill(probe["pid"],signal.SIGTERM)
        result["fixture_stopped_settings_retained"] = True
    finally:
        if client:
            if helper and helper.poll() is None:
                try:
                    client.post("/api/close",json={})
                    helper.wait(30)
                except (httpx.HTTPError,subprocess.TimeoutExpired):
                    result["helper_needs_attention"] = True
            client.close()
        if log:
            log.close()
        after = snapshot(list(before))
        result["existing_containers_unchanged"] = before == after
        result["protected_count"] = len(before)
        (output / "report.json").write_text(json.dumps(result,indent=2))
        assert before == after
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--caddy",type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.package,args.output,args.caddy),indent=2))
