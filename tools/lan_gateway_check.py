"""Isolated packaged LAN/rollback acceptance; never changes host networking/startup.

Creates one new dashboard/controller and loopback-only Caddy. Existing containers
are compared before/after. No personal apps, credentials or media are connected.
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import time
from pathlib import Path

import httpx

from stackarr.lan_gateway import environment, prepare, verified
from stackarr.self_update import SelfUpdates, read


def run(command, timeout=180):
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise RuntimeError("Acceptance subprocess failed: " + result.stdout[-500:] + result.stderr[-500:])
    return result.stdout.strip()


def docker(*args):
    return run(["docker", *args])


def snapshot(identities=None):
    identities = identities or docker("ps", "-aq", "--no-trunc").split()
    if not identities:
        return {}
    result = {}
    for row in json.loads(docker("inspect", *identities)):
        # No environment variables or credentials enter the evidence.
        result[row["Id"]] = {"image": row["Image"], "started": row["State"]["StartedAt"],
                             "restarts": row["RestartCount"], "mounts": row["Mounts"],
                             "ports": row["HostConfig"]["PortBindings"],
                             "project": row["Config"].get("Labels", {}).get("com.docker.compose.project")}
    return result


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait(predicate, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, httpx.HTTPError, ValueError):
            pass
        time.sleep(.3)
    raise TimeoutError("Isolated acceptance deadline exceeded")


def job_done(updates, identity):
    def check():
        value = read(updates.home / "jobs" / identity / "job.json")
        return value if value["phase"] in {"succeeded", "rolled-back", "failed-recovered", "needs-recovery"} else None
    return wait(check, 240)


def assert_preserved(previous, current, path="config"):
    """Permit new schema defaults, but never changed or removed saved values."""
    if isinstance(previous, dict):
        assert isinstance(current, dict), path
        for key, value in previous.items():
            assert key in current, path + "." + key
            assert_preserved(value, current[key], path + "." + key)
    else:
        assert previous == current, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--source-package", type=Path, help="Rehearse adoption/update from this older package in new isolated state")
    parser.add_argument("--powershell", default="powershell.exe", help="Launcher shell; older packages may require PowerShell 7 quoting")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, default=Path(shutil.which("caddy") or "caddy.exe"))
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() or not root.is_relative_to(Path("test-results").resolve()):
        raise ValueError("Choose a new acceptance folder under test-results.")
    root.mkdir(parents=True)
    before = snapshot()
    (root / "before-private.json").write_text(json.dumps(before), encoding="utf-8")
    port, controller_port, gateway_port = free_port(), free_port(), free_port()
    assert len({port, controller_port, gateway_port}) == 3
    state, package = root / "state", args.package.resolve()
    source_package = args.source_package.resolve() if args.source_package else package
    caddy_child = None
    gateway_output = None
    result = {"scope": "isolated-packaged-loopback-https", "checks": {},
              "signed_out_boot": "not-run-no-disposable-host", "second_device": "not-run",
              "browser_trust_store": "not-modified", "firewall_dns_startup": "not-modified"}
    try:
        run([args.powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", source_package / "Start-StackarrPreview.ps1",
             "-StateDirectory", state, "-Port", port, "-ControllerPort", controller_port, "-NoBrowser"], timeout=300)
        installation = read(state / "installation.json")
        port, controller_port = installation["port"], installation["controller_port"]
        assert installation["project"] not in {row["project"] for row in before.values()}
        os.environ.update(STACKARR_PORT=str(port), STACKARR_CONTROLLER_PORT=str(controller_port))
        updates = SelfUpdates(state, package_root=source_package)
        active = updates.active()
        assert active["project"] == installation["project"]
        origin = f"http://localhost:{port}"
        password = secrets.token_urlsafe(28)
        (root / "access-private.json").write_text(json.dumps({"origin": origin, "password": password}), encoding="utf-8")
        with httpx.Client(base_url=origin, trust_env=False, timeout=15) as local:
            token = docker("exec", active["project"], "cat", "/var/lib/stackarr/setup-token")
            response = local.post("/api/setup", json={"password": password, "setup_token": token}, headers={"Origin": origin})
            assert response.status_code == 200
            assert local.post("/api/login", json={"password": password}, headers={"Origin": origin}).status_code == 200
            config = local.get("/api/config").json()["config"]
            source_config = config
            if args.source_package:
                result["source_release"] = read(source_package / "manifest.json")["release"]
                updates.admit(package.with_suffix(".zip"))
                upgrade = updates.approve(updates.review("update"))
                upgraded = job_done(updates, upgrade["id"])
                (root / "upgrade-job-private.json").write_text(json.dumps(upgraded), encoding="utf-8")
                assert upgraded["phase"] == "succeeded", upgraded.get("failure", upgraded["message"])
                current_config = local.get("/api/config").json()["config"]
                assert_preserved(config, current_config)
                config = current_config
                active = updates.active()
                result["checks"]["older_preview_adoption_update_preserves_session_settings"] = True
            protected = updates.protected(active)
            remote = f"https://127.0.0.1:{gateway_port}"
            gateway = root / "gateway"
            prepare(gateway, {"origin": remote, "bind": "127.0.0.1", "clients": ["127.0.0.1/32"],
                              "dashboard_port": port, "apps": {}, "lab": True, "state_root": str(state)},
                    args.caddy.resolve())
            review_file, job_file = root / "lan-review-private.json", root / "lan-result-private.json"
            run([package / "StackarrPreview.exe", "--lan-review", gateway, "--maintenance-report", review_file])
            run([package / "StackarrPreview.exe", "--lan-apply", review_file, "--maintenance-report", job_file])
            job = read(job_file)
            outcome = job_done(updates, job["id"])
            (root / "lan-job-private.json").write_text(json.dumps(outcome), encoding="utf-8")
            assert outcome["phase"] == "succeeded", outcome.get("failure", outcome["message"])
            result["checks"]["packaged_lan_checkpoint"] = True
            assert local.get("/api/config").json()["config"] == config
            assert updates.protected(updates.active())["dashboard"] == protected["dashboard"]
            result["checks"]["local_session_settings_preserved"] = True
            gateway_output = (gateway / "private" / "acceptance-gateway.log").open("ab")

            def start_gateway():
                verified(gateway)
                return subprocess.Popen([str(gateway / "caddy.exe"), "run", "--config", str(gateway / "Caddyfile"), "--adapter", "caddyfile"],
                                        env=environment(gateway), stdout=gateway_output, stderr=gateway_output,
                                        creationflags=subprocess.CREATE_NO_WINDOW)

            caddy_child = start_gateway()
            root_ca = wait(lambda: next(iter((gateway / "private").rglob("root.crt")), None))
            ca_hash = hashlib.sha256(root_ca.read_bytes()).hexdigest()
            context = ssl.create_default_context(cafile=str(root_ca))
            with httpx.Client(base_url=remote, verify=context, trust_env=False, timeout=15) as client:
                wait(lambda: client.get("/healthz").status_code == 200)
                try:
                    httpx.get(remote + "/healthz", trust_env=False, timeout=5)
                    raise AssertionError("Untrusted CA was accepted")
                except httpx.ConnectError:
                    result["checks"]["untrusted_ca_rejected"] = True
                assert client.get("/api/config").status_code == 401
                response = client.post("/api/login", json={"password": password}, headers={"Origin": remote})
                assert response.status_code == 200
                assert all(flag in response.headers["set-cookie"] for flag in ("Secure", "HttpOnly", "SameSite=strict"))
                csrf = response.json()["csrf"]
                assert client.get("/api/config").json()["config"] == config
                assert client.post("/api/logout", headers={"Origin": origin, "X-CSRF-Token": csrf}).status_code == 403
                assert client.post("/api/logout", headers={"Origin": remote}).status_code == 403
                assert client.post("/api/setup/handoff", json={"ticket": "fake"}, headers={"Origin": remote}).status_code == 403
                result["checks"]["trusted_tls_login_csrf_local_approval"] = True
                with httpx.Client(transport=httpx.HTTPTransport(verify=context, local_address="127.0.0.2"), trust_env=False) as outsider:
                    assert outsider.get(remote + "/healthz").status_code == 403
                result["checks"]["unlisted_client_rejected"] = True
                assert client.get("/healthz", headers={"Host": "attacker.home.arpa", "X-Forwarded-Host": url_authority(remote)}).status_code != 200
                result["checks"]["spoofed_host_rejected"] = True
                # Restart only processes/containers created by this run.
                caddy_child.terminate()
                caddy_child.wait(15)
                caddy_child = start_gateway()
                wait(lambda: client.get("/api/config").status_code == 200)
                assert hashlib.sha256(root_ca.read_bytes()).hexdigest() == ca_hash
                docker("stop", active["project"])
                updates.start()
                wait(lambda: client.get("/api/config").status_code == 200)
                assert client.get("/api/config").json()["config"] == config
                result["checks"]["gateway_dashboard_restart_keeps_ca_session_settings"] = True
                rollback = updates.approve(updates.review("rollback", job["id"]))
                outcome = job_done(updates, rollback["id"])
                assert outcome["phase"] == "rolled-back", outcome.get("failure", outcome["message"])
                assert local.get("/api/config").json()["config"] == config
                assert client.get("/api/config").status_code == 400
                result["checks"]["actual_rollback_revokes_lan_preserves_local"] = True
                if args.source_package:
                    downgrade = updates.approve(updates.review("rollback", upgrade["id"]))
                    restored = job_done(updates, downgrade["id"])
                    assert restored["phase"] == "rolled-back", restored.get("failure", restored["message"])
                    assert local.get("/api/config").json()["config"] == source_config
                    assert updates.active()["release"] == upgraded["source"]["release"]
                    result["checks"]["separate_package_rollback_restores_older_release"] = True
            (root / "access-private.json").write_text(json.dumps({"origin": origin, "password": password}), encoding="utf-8")
            result["retained_local_origin"] = origin
    finally:
        if caddy_child and caddy_child.poll() is None:
            caddy_child.terminate()
            caddy_child.wait(15)
        if gateway_output:
            gateway_output.close()
        after = snapshot(list(before))
        result["existing_containers_unchanged"] = before == after
        result["protected_count"] = len(before)
        (root / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        assert before == after, "A pre-existing container changed; inspect preservation evidence."
    print(json.dumps(result, indent=2))


def url_authority(url):
    from urllib.parse import urlsplit
    return urlsplit(url).netloc


if __name__ == "__main__":
    main()
