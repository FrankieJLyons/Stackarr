"""Host-local guided LAN preparation and scoped recovery; no OS network changes."""

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from .backup_policy import direct
from .deployment import DeploymentError
from .lan import LanAccess
from .lan_gateway import environment, prepare, private_address, resume, verified
from .self_update import ID, TERMINAL, SelfUpdates, digest, pending, read, write
from .store import Conflict

PHYSICAL = ["Another computer: trusted browser sign-in and app/Plex playback",
            "Spare host: cold boot while Windows stays signed out"]


def setup_origin(address, port, hostname=""):
    """Use a portable IP by default; an optional local name needs LAN DNS."""
    address = private_address(address)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Choose an HTTPS port between 1024 and 65535.")
    if not isinstance(hostname, str):
        raise ValueError("Use a local computer name, or leave it blank to use the IP address.")
    hostname = hostname.strip().lower()
    if hostname:
        labels = hostname.split(".")
        if (len(hostname) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
                or not (len(labels) == 1 or hostname.endswith((".home.arpa", ".local")))
                or hostname in {"localhost", "local", "home.arpa"} or hostname.isdigit()):
            raise ValueError("Use a local computer name such as media-server, media-server.local or media-server.home.arpa. Leave it blank to use the IP address.")
    return f"https://{hostname or address}:{port}"


def operation_fingerprint(value):
    return hashlib.sha256(json.dumps({key:value.get(key) for key in ("action", "source", "network", "snapshot")}, sort_keys=True).encode()).hexdigest()


def bundled_caddy():
    root = Path(sys._MEIPASS) / "lan_caddy" if getattr(sys, "frozen", False) else Path(__file__).parent / "lan_caddy"
    return root / "caddy.exe"


def checked_caddy(path):
    path = direct(Path(path).absolute())
    lock = read(Path(__file__).parent / "caddy.lock.json")
    if not path.is_file() or digest(path) != lock["binary_sha256"]:
        raise ValueError("The secure gateway is missing or changed. Re-extract the complete LAN setup package, then reopen setup.")
    return path


def interfaces():
    """Read connected physical interfaces only. Never alter a network profile."""
    if os.name != "nt":
        return []
    script = """$ErrorActionPreference='Stop'; $rows=@(Get-NetIPConfiguration | Where-Object {$_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway} | ForEach-Object { $n=$_; foreach($a in $n.IPv4Address) { [pscustomobject]@{name=$n.InterfaceAlias;address=$a.IPAddress;prefix=$a.PrefixLength;profile=[string]$n.NetProfile.NetworkCategory} } }); ConvertTo-Json -InputObject $rows -Compress"""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], capture_output=True,
                            text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or len(result.stdout) > 32768:
        return []
    rows = json.loads(result.stdout)
    choices = []
    for row in rows:
        try:
            address = private_address(row["address"])
            network = ipaddress.ip_network(f"{address}/{int(row['prefix'])}", strict=False)
            if network.prefixlen < 16:
                continue
            choices.append({"name": str(row["name"])[:80], "address": address,
                            "clients": str(network), "profile": row["profile"]})
        except (KeyError, TypeError, ValueError):
            continue
    return choices


class LanSetup:
    def __init__(self, state, workspace, caddy=None, *, network_reader=interfaces, updates_factory=SelfUpdates):
        self.state, self.root = direct(Path(state).absolute()), direct(Path(workspace).absolute())
        if self.root == self.state or self.root.is_relative_to(self.state) or self.state.is_relative_to(self.root):
            raise ValueError("Keep home-network setup in its own folder outside the installation.")
        # Opening setup never adopts or starts the selected installation.
        installation = read(self.state / "installation.json")
        if installation.get("owner") != "stackarr-docker-preview-v1" or type(installation.get("port")) is not int:
            raise ValueError("Choose an existing Stackarr installation. Its saved installation record is needed.")
        self.local = f"http://localhost:{installation['port']}"
        self.port = installation["port"]
        self.caddy = Path(caddy) if caddy else bundled_caddy()
        self.network_reader, self.updates_factory = network_reader, updates_factory
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.journal = self.root / "setup.json"
        if self.journal.exists():
            self.saved = read(self.journal)
            if self.saved.get("schema") != 1 or self.saved.get("state") != str(self.state):
                raise ValueError("This setup folder belongs to another installation.")
        else:
            if any(self.root.iterdir()):
                raise ValueError("Choose an empty home-network setup folder.")
            self.saved = {"schema": 1, "state": str(self.state), "bundle": None, "job": None, "checks": {}}
            self.save()
        self.reviewed = None
        self.child = None
        self.log = None

    def save(self):
        write(self.journal, self.saved)

    def bundle(self):
        identity = self.saved.get("bundle")
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            raise ValueError("Prepare your home-network address first.")
        root, manifest = verified(self.root / identity)
        if manifest["request"]["state_root"] != str(self.state) or manifest["request"]["dashboard_port"] != self.port:
            raise ValueError("The prepared address belongs to a different installation. Prepare it again.")
        return root, manifest

    def updates(self):
        if not (self.state / "stackarr-runtime.json").is_file():
            raise ValueError("First use Settings to review an update to a LAN-capable Stackarr package. Preparation is saved; this installation has not been changed.")
        return self.updates_factory(self.state)

    def job(self):
        intent = self.saved.get("intent")
        if intent:
            current = pending(self.state)
            if current and current["created"] >= intent["created"] and operation_fingerprint(current) == intent["fingerprint"]:
                self.saved["job"] = current["id"]
                self.saved.pop("intent", None)
                self.save()
        identity = self.saved.get("job")
        if not identity:
            return None
        if not ID.fullmatch(identity):
            raise ValueError("The saved recovery record needs inspection. Keep your setup folder.")
        value = read(self.state / "stackarr-maintenance/jobs" / identity / "job.json")
        return {key: value.get(key) for key in ("id", "phase", "message", "action")}

    def status(self):
        issues = []
        try:
            job = self.job()
        except Exception:
            job = None
            issues.append("The saved operation needs inspection. Open the local dashboard to review maintenance recovery; keep the setup folder.")
        running = bool(self.child and self.child.poll() is None)
        result = {"local_url": self.local, "prepared": False, "issues": issues,
                  "gateway_running": running, "job": job, "checks": self.saved.get("checks", {}),
                  "physical_checks": PHYSICAL, "physical_status": "pending", "reboot_status": "not-certified"}
        if self.saved.get("bundle"):
            try:
                _, manifest = self.bundle()
                result.update(prepared=True, address=manifest["network"]["origin"], clients=manifest["request"]["clients"], certificate=None)
                result["certificate"] = self.certificate()[1]
            except Exception as exc:
                issues.append(public_error(exc))
        return result

    def choices(self):
        checked_caddy(self.caddy)
        return {"interfaces": self.network_reader(), "port": 29443, "local_url": self.local}

    def prepare(self, values):
        if not {"address", "clients", "port"} <= set(values) or set(values) - {"address", "clients", "port", "hostname"}:
            raise ValueError("Choose a server address, allowed home network and HTTPS port.")
        origin = setup_origin(values["address"], values["port"], values.get("hostname", ""))
        if self.saved.get("bundle"):
            _, previous = self.bundle()
            request = previous["request"]
            if (request["bind"] == values["address"] and request["clients"] == [values["clients"]]
                    and request["origin"] == origin):
                return self.status()
        if self.child and self.child.poll() is None:
            raise Conflict("Stop this setup's gateway before preparing a different address.")
        job = self.job()
        if job and job["phase"] not in TERMINAL:
            raise Conflict("Finish or recover the current operation before changing the address.")
        if self.saved.get("bundle") and (self.state / "stackarr-runtime.json").exists():
            runtime = read(self.state / "stackarr-runtime.json")
            if runtime["plan"]["services"]["stackarr"]["environment"].get("STACKARR_LAN_ORIGIN"):
                raise Conflict("Turn off the current home-network address before preparing another one. Keep its certificate and recovery checkpoint.")
        address = private_address(values["address"])
        port = values["port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Choose an HTTPS port between 1024 and 65535.")
        identity = uuid.uuid4().hex
        prepare(self.root / identity, {"origin": origin, "bind": address,
                "clients": [values["clients"]], "dashboard_port": self.port, "apps": {}, "state_root": str(self.state)}, checked_caddy(self.caddy))
        self.saved.update(bundle=identity, job=None, checks={})
        self.saved.pop("certificate", None)
        self.reviewed = None
        self.save()
        self.certificate()
        return self.status()

    def certificate(self):
        root, _ = self.bundle()
        paths = list((root / "private").rglob("root.crt"))
        if len(paths) != 1:
            raise ValueError("The public certificate is missing. Keep the existing setup folder and recover its certificate; do not replace a trusted certificate silently.")
        path = direct(paths[0])
        if path.stat().st_size > 16384:
            raise ValueError("The certificate needs inspection.")
        cert = x509.load_pem_x509_certificate(path.read_bytes())
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca or cert.not_valid_after_utc <= datetime.now(timezone.utc):
            raise ValueError("The certificate has expired or is not a certificate authority. Keep the existing setup and ask for certificate recovery.")
        data = cert.public_bytes(serialization.Encoding.DER)
        fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
        expected = self.saved.get("certificate")
        if expected and expected != fingerprint:
            raise ValueError("The certificate changed. Home access is blocked until its identity is reviewed on each client.")
        if not expected:
            self.saved["certificate"] = fingerprint
            self.save()
        return data, {"fingerprint": fingerprint, "expires": cert.not_valid_after_utc.date().isoformat()}

    def download(self):
        data, info = self.certificate()
        return {"filename": "Stackarr-home-certificate.cer", "data": base64.b64encode(data).decode(), **info}

    def review(self, action):
        if action not in {"enable", "undo", "recover"}:
            raise ValueError("Choose enable, turn off home access, or recover an interrupted operation.")
        root, manifest = self.bundle()
        if action == "enable":
            self.certificate()
        updates = self.updates()
        if action == "enable":
            value = updates.review("lan", manifest["network"])
        elif action == "undo":
            runtime = updates.active()
            env = runtime["plan"]["services"]["stackarr"]["environment"]
            if env.get("STACKARR_LAN_ORIGIN") != manifest["network"]["origin"]:
                raise Conflict("This home-network address is already off or another address is active. No settings were restored.")
            jobs = [j for j in updates.jobs() if j.get("action") == "lan" and j.get("network") == manifest["network"] and j.get("phase") == "succeeded"]
            if not jobs:
                raise Conflict("The LAN rollback checkpoint is unavailable. Keep your settings and recovery files; do not reset the installation.")
            value = updates.review("rollback", jobs[0]["id"])
        else:
            current = pending(self.state)
            if not current or current["id"] != self.saved.get("job"):
                raise Conflict("There is no interrupted operation from this setup to recover.")
            value = updates.review("recover", current["id"])
        token = secrets.token_urlsafe(32)
        self.reviewed = {"token": token, "expires": time.monotonic() + 300, "bundle_hash": digest(root / "gateway.json"),
                         "review": value, "action": action}
        return {"token": token, "action": action, "notice": value["notice"], "local_url": self.local,
                "address": manifest["network"]["origin"], "physical_checks": PHYSICAL}

    def apply(self, token):
        saved, self.reviewed = self.reviewed, None
        if (not saved or not isinstance(token, str) or not secrets.compare_digest(saved["token"], token)
                or saved["expires"] <= time.monotonic()):
            raise Conflict("This review expired or was already used. Review the change again.")
        root, _ = self.bundle()
        if saved["action"] == "enable":
            self.certificate()
        if digest(root / "gateway.json") != saved["bundle_hash"]:
            raise Conflict("The prepared address changed. Review it again.")
        if saved["action"] != "enable":
            self.stop()
        if saved["action"] != "recover":
            self.saved["intent"] = {"created": time.time(), "fingerprint": operation_fingerprint(saved["review"])}
            self.save()
        job = self.updates().approve(saved["review"])
        self.saved["job"] = job["id"]
        self.saved.pop("intent", None)
        self.save()
        return self.status()

    def check(self):
        from .docker_runtime import inspect

        self.bundle()
        self.certificate()
        runtime = inspect(enabled=True)
        self.saved["checks"] = {"docker_ready": runtime["state"] == "ready", "checked_at": time.time(),
                                "message": "Docker is ready. You can review activation or start the prepared gateway." if runtime["state"] == "ready" else
                                "Open Docker Desktop on this computer, wait for its engine, then check again. Your saved setup is kept."}
        self.save()
        return self.status()

    def start(self):
        root, manifest = self.bundle()
        self.certificate()
        updates = self.updates()
        runtime = updates.active()
        env = runtime["plan"]["services"]["stackarr"]["environment"]
        access = LanAccess(env["STACKARR_ORIGIN"], env)
        if {"origin": access.origin, "links": access.links} != manifest["network"]:
            raise Conflict("Review and enable this address first. The gateway has not started.")
        if self.child and self.child.poll() is None:
            return self.status()
        self.stop()
        resume(root)
        self.log = (root / "private/wizard-gateway.log").open("ab")
        self.child = subprocess.Popen([str(root / "caddy.exe"), "run", "--config", str(root / "Caddyfile"), "--adapter", "caddyfile"],
                         env=environment(root), stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        cert, _ = self.certificate()
        context = ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(cert))
        deadline = time.monotonic() + 15
        with httpx.Client(verify=context, trust_env=False, timeout=2) as client:
            while self.child.poll() is None and time.monotonic() < deadline:
                try:
                    response = client.get(manifest["network"]["origin"] + "/healthz")
                    if response.status_code == 200 and response.json().get("status") == "ok":
                        return self.status()
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(.2)
        self.stop()
        raise ValueError("The secure gateway could not start. Check that the saved server address still belongs to this computer and its port is free. Existing services were left running.")

    def stop(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            self.child.wait(timeout=15)
        self.child = None
        if self.log:
            self.log.close()
            self.log = None
        return {"gateway_running": False, "message": "This setup's gateway is stopped. Settings and certificates are kept."}

    def dispatch(self, action, values):
        if action == "prepare":
            return self.prepare(values)
        if action == "review" and set(values) == {"action"}:
            return self.review(values["action"])
        if action == "apply" and set(values) == {"token"}:
            return self.apply(values["token"])
        if action in {"status", "choices", "certificate", "check", "start", "stop"} and not values:
            return {"certificate": self.download}.get(action, getattr(self, action, None))()
        raise ValueError("Choose one of the home-network setup steps.")


def public_error(exc):
    if isinstance(exc, (ValueError, DeploymentError, Conflict)):
        return str(exc)
    return "This step could not finish. Keep your setup folder, restore Docker and folder access, then try again. Existing apps and media are retained."
