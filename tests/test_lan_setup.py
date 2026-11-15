import base64
import copy
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from stackarr.lan_gateway import gateway_config
from stackarr.lan_setup import LanSetup, operation_fingerprint, setup_origin
from stackarr.lan_setup_server import LanSetupServer
from stackarr.self_update import digest, read, write
from stackarr.store import Conflict


def certificate(path):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic LAN test CA")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
            .sign(key, hashes.SHA256()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = tmp_path / "installation"
    state.mkdir()
    write(state / "installation.json", {"owner": "stackarr-docker-preview-v1", "port": 29001})
    calls = []

    class Updates:
        def review(self, action, identity=None):
            calls.append(("review", action))
            return {"action": action, "network": copy.deepcopy(identity), "notice": "Synthetic settings checkpoint review."}

        def approve(self, review):
            calls.append(("approve", review["action"]))
            identity = "a" * 32
            folder = state / "stackarr-maintenance/jobs" / identity
            folder.mkdir(parents=True, exist_ok=True)
            write(folder / "job.json", {"id": identity, "action": review["action"], "phase": "succeeded", "message": "Checked settings preserved."})
            return {"id": identity}

    binary = "caddy.exe" if os.name == "nt" else "caddy"

    def prepare(root, request, executable):
        root.mkdir()
        (root / binary).write_bytes(b"synthetic executable; never run")
        (root / "Caddyfile").write_text(gateway_config(**{k:v for k,v in request.items() if k != "state_root"}), encoding="utf-8")
        manifest = {"schema": 1, "request": request, "network": {"origin": request["origin"], "links": {}},
                    "files": {name:digest(root / name) for name in (binary, "Caddyfile")}}
        write(root / "gateway.json", manifest)
        certificate(root / "private/root.crt")
        return manifest

    monkeypatch.setattr("stackarr.lan_setup.checked_caddy", lambda p: p)
    monkeypatch.setattr("stackarr.lan_setup.prepare", prepare)
    service = LanSetup(state, tmp_path / "network", tmp_path / binary, network_reader=lambda: [], updates_factory=lambda _: Updates())
    service.calls = calls
    return service


def prepared(setup):
    return setup.prepare({"address": "172.20.50.10", "clients": "172.20.50.0/24", "port": 29443})


@pytest.mark.parametrize("hostname", ["example-pc", "media-server.local", "media.home.arpa"])
def test_optional_local_name_keeps_private_bind_and_certificate_identity(setup, hostname):
    values = {"address": "172.20.50.10", "clients": "172.20.50.0/24", "port": 29443, "hostname": hostname}
    status = setup.prepare(values)
    assert status["address"] == f"https://{hostname}:29443"
    _, manifest = setup.bundle()
    assert manifest["request"]["bind"] == "172.20.50.10"
    assert setup.prepare(values)["certificate"] == status["certificate"]
    assert not setup.child and not setup.calls


@pytest.mark.parametrize("hostname", ["localhost", "local", "home.arpa", "12345", "evil.example.com", "a..local", "-host", "host-", "host/path", "host:443", "host\nreverse_proxy attacker", 1])
def test_local_name_rejects_unusable_names_and_injection(hostname):
    with pytest.raises(ValueError, match="local computer name"):
        setup_origin("172.20.50.10", 29443, hostname)


def test_prepare_preserves_unadopted_installation_and_exports_only_public_der(setup):
    before = {p.name:p.read_bytes() for p in setup.state.iterdir()}
    status = prepared(setup)
    assert status["prepared"] and not status["gateway_running"]
    assert status["physical_status"] == "pending" and status["reboot_status"] == "not-certified"
    assert before == {p.name:p.read_bytes() for p in setup.state.iterdir()}
    download = setup.download()
    public = base64.b64decode(download["data"])
    cert = x509.load_der_x509_certificate(public)
    assert cert.fingerprint(hashes.SHA256()).hex().upper() == download["fingerprint"]
    assert b"PRIVATE KEY" not in public
    with pytest.raises(ValueError, match="review an update"):
        setup.review("enable")
    assert not setup.calls


def test_saved_setup_reopens_with_same_certificate_and_no_runtime_calls(setup):
    status = prepared(setup)
    again = LanSetup(setup.state, setup.root)
    assert again.status()["certificate"] == status["certificate"]
    assert not again.child and not setup.calls
    assert prepared(setup)["certificate"] == status["certificate"]


def test_interrupted_handoff_rediscovers_only_its_matching_pending_job(setup):
    prepared(setup)
    value = {"action":"lan", "source":{"release":"synthetic"}, "network":{"origin":"https://172.20.50.10:29443", "links":{}}, "snapshot":None}
    setup.saved["intent"] = {"created":time.time()-1, "fingerprint":operation_fingerprint(value)}
    setup.save()
    identity = "b"*32
    home = setup.state / "stackarr-maintenance"
    (home / "jobs" / identity).mkdir(parents=True)
    write(home / "active-job.json", {"id":identity})
    write(home / "jobs" / identity / "job.json", value | {"id":identity, "created":time.time(), "phase":"needs-recovery", "message":"Interrupted"})
    reopened = LanSetup(setup.state, setup.root)
    assert reopened.job()["id"] == identity and reopened.saved["job"] == identity
    assert "intent" not in reopened.saved


def test_review_is_one_use_expiring_and_does_not_claim_physical_acceptance(setup):
    prepared(setup)
    write(setup.state / "stackarr-runtime.json", {})
    review = setup.review("enable")
    assert len(review["physical_checks"]) == 2
    assert setup.calls == [("review", "lan")]
    result = setup.apply(review["token"])
    assert result["job"]["phase"] == "succeeded" and result["physical_status"] == "pending"
    with pytest.raises(Conflict, match="already used"):
        setup.apply(review["token"])
    review = setup.review("enable")
    setup.reviewed["expires"] = time.monotonic() - 1
    with pytest.raises(Conflict, match="expired"):
        setup.apply(review["token"])
    assert setup.calls.count(("approve", "lan")) == 1


def test_changed_bundle_and_certificate_fail_before_approval(setup):
    prepared(setup)
    write(setup.state / "stackarr-runtime.json", {})
    review = setup.review("enable")
    root, _ = setup.bundle()
    certificate(root / "private/root.crt")
    with pytest.raises(ValueError, match="certificate changed"):
        setup.apply(review["token"])
    assert ("approve", "lan") not in setup.calls
    (root / "Caddyfile").write_text("changed")
    status = setup.status()
    assert "Gateway files changed" in status["issues"][0]
    assert status["local_url"] == setup.local and not status["prepared"]


def test_missing_certificate_keeps_local_recovery_and_allows_reviewed_undo(setup):
    prepared(setup)
    root, manifest = setup.bundle()
    (root / "private/root.crt").unlink()
    status = setup.status()
    assert status["local_url"] == setup.local and status["certificate"] is None
    assert "missing" in status["issues"][0]
    write(setup.state / "stackarr-runtime.json", {})
    updates = setup.updates_factory(setup.state)
    updates.active = lambda:{"plan":{"services":{"stackarr":{"environment":{"STACKARR_LAN_ORIGIN":manifest['network']['origin']}}}}}
    updates.jobs = lambda:[{"id":"b"*32,"action":"lan","network":manifest["network"],"phase":"succeeded"}]
    setup.updates_factory = lambda _:updates
    review = setup.review("undo")
    assert setup.apply(review["token"])["job"]["phase"] == "succeeded"


@pytest.mark.parametrize("values", [
    {"address":"8.8.8.8", "clients":"172.20.50.0/24", "port":29443},
    {"address":"172.20.50.10", "clients":"0.0.0.0/0", "port":29443},
    {"address":"172.20.50.10", "clients":"172.20.50.0/24", "port":True},
    {"address":"172.20.50.10", "clients":"172.20.50.0/24", "port":29443, "state":"arbitrary"},
])
def test_no_public_listener_broad_subnet_or_arbitrary_state(setup, values):
    with pytest.raises(ValueError):
        setup.prepare(values)
    assert not setup.saved["bundle"] and not setup.calls


def test_workspace_cannot_overlap_installation_or_change_owner(setup):
    with pytest.raises(ValueError, match="outside"):
        LanSetup(setup.state, setup.state / "inside")
    saved = read(setup.journal)
    saved["state"] = str(setup.root)
    write(setup.journal, saved)
    with pytest.raises(ValueError, match="another installation"):
        LanSetup(setup.state, setup.root)


def test_stop_never_uses_a_recorded_pid_or_changes_receipts(setup):
    prepared(setup)
    before = setup.journal.read_bytes()
    assert setup.stop()["gateway_running"] is False
    assert before == setup.journal.read_bytes()


def test_local_server_rejects_cross_site_paths_and_unauthorized_certificates(setup):
    prepared(setup)
    with LanSetupServer(setup) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=server.origin, trust_env=False) as client:
                page = client.get("/")
                assert page.status_code == 200 and server.key not in page.text
                assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
                assert client.get("/api/certificate").status_code == 404
                headers = {"Origin":server.origin, "X-LAN-Key":server.key}
                assert client.post("/api/certificate", json={}).status_code == 403
                assert client.post("/api/certificate", json={}, headers=headers | {"Origin":"https://untrusted.invalid"}).status_code == 403
                assert client.post("/api/prepare", json={}, headers=headers | {"Host":"untrusted.invalid"}).status_code == 403
                assert client.post("/api/status", json={"path":"private/root.key"}, headers=headers).status_code == 409
                assert client.get("/private/root.key").status_code == 404
                assert client.post("/api/status", json={}, headers=headers).json()["physical_status"] == "pending"
                assert client.post("/api/certificate", json={}, headers=headers).json()["filename"].endswith(".cer")
                assert client.post("/api/status", content=b"x"*2049, headers=headers | {"Content-Type":"application/json"}).status_code == 400
                duplicate = list(headers.items()) + [("Origin", server.origin)]
                assert client.post("/api/status", json={}, headers=duplicate).status_code == 403
        finally:
            server.shutdown()
            thread.join(3)
    assert not setup.calls
