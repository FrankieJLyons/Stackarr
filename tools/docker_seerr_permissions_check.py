"""Real pinned Seerr permission/session checks with isolated test identities."""

import argparse
import base64
import datetime
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes as crypto_hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from stackarr.deployment import images
from stackarr.docker_runtime import executable
from stackarr.self_update import read, write
from tools import docker_app_maintenance_check as preservation
from tools.docker_folder_ports_check import command

ROOT = Path("test-results/docker-seerr-permissions-20261019-r1").resolve()
PROJECT = "stackarr-seerr-permissions-20261019-r1"
ORIGIN = "http://seerr:5055"
CONTROL = "http://identity:8888"
FIXTURE_IMAGE = "sha256:296b42b6512c18b6f396772abb0dae6c17f53508d04294e8febcdfef361d2f34"

BRIDGE = """import base64,json,sys,httpx
r=json.load(sys.stdin)
assert r['url'].startswith(('http://seerr:5055/','http://identity:8888/'))
with httpx.Client(trust_env=False,timeout=20) as c:
 response=c.request(r['method'],r['url'],headers=r['headers'],content=base64.b64decode(r['body']))
 print(json.dumps({'status':response.status_code,'headers':response.headers.multi_items(),'body':base64.b64encode(response.content).decode()}))
"""


class InternalHTTP(httpx.BaseTransport):
    """Real HTTP inside the lab network; preserves normal cookies and headers."""

    def handle_request(self, request):
        value = {"method": request.method, "url": str(request.url), "headers": list(request.headers.multi_items()),
                 "body": base64.b64encode(request.read()).decode()}
        result = subprocess.run([executable(), "exec", "-i", PROJECT + "-identity-1", "python", "-c", BRIDGE],
            input=json.dumps(value), capture_output=True, text=True, timeout=35)
        if result.returncode:
            raise httpx.ConnectError("The isolated HTTP bridge did not respond")
        reply = json.loads(result.stdout)
        return httpx.Response(reply["status"], headers=reply["headers"], content=base64.b64decode(reply["body"]))


def preserved():
    preservation.OUTPUT = ROOT
    preservation.main_preserved()


def report(case, **proof):
    preserved()
    saved = read(ROOT / "native-report.json") if (ROOT / "native-report.json").exists() else {"cases": []}
    assert case not in {row["case"] for row in saved["cases"]}
    saved["cases"].append({"case": case, "passed": True, "main_preserved": True, **proof})
    write(ROOT / "native-report.json", saved)
    print("Seerr permission check passed: " + case, flush=True)


def prepare():
    assert not (ROOT / "main-before.json").exists()
    write(ROOT / "main-before.json", preservation.main_snapshot())
    write(ROOT / "volumes-before.json", command(["volume", "ls", "-q"]).split())
    fixture = ROOT / "fixture"
    fixture.mkdir()
    state = ROOT / "fixture-state"
    state.mkdir()
    shutil.copyfile("tools/seerr_accounts_fixture.py", fixture / "server.py")
    now = datetime.datetime.now(datetime.UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Stackarr isolated identity test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=7)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, crypto_hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "plex.tv")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=7))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("plex.tv")]), critical=False)
            .sign(ca_key, crypto_hashes.SHA256()))
    (fixture / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (fixture / "plex.tv.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (fixture / "plex.tv.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    accounts = [{"id": 9700100 + number, "name": name, "token": secrets.token_urlsafe(32)}
                for number, name in enumerate(("fixture-owner", "fixture-shared", "fixture-unshared", "fixture-imported"), 1)]
    write(fixture / "access.json", {"accounts": accounts})
    write(state / "membership.json", {"shared": [9700102, 9700104], "revoked": [], "events": {}})
    compose = {"services": {
        "identity": {"image": FIXTURE_IMAGE, "entrypoint": ["python", "-B", "/fixture/server.py"],
            "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "volumes": [{"type": "bind", "source": str(fixture), "target": "/fixture", "read_only": True},
                        {"type": "bind", "source": str(state), "target": "/state"}],
            "ports": [{"host_ip": "127.0.0.1", "published": "43851", "target": 8888}],
            "networks": {"isolated": {"aliases": ["plex.tv"]}}},
        "seerr": {"image": images()["seerr"], "platform": "linux/amd64", "init": True,
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "environment": {"TZ": "Etc/UTC", "LOG_LEVEL": "info", "NODE_EXTRA_CA_CERTS": "/test/ca.pem"},
            "volumes": [{"type": "volume", "source": "seerr-config", "target": "/app/config"},
                        {"type": "bind", "source": str(fixture / "ca.pem"), "target": "/test/ca.pem", "read_only": True}],
            "ports": [{"host_ip": "127.0.0.1", "published": "43850", "target": 5055}], "networks": ["isolated"]}},
        "volumes": {"seerr-config": {}}, "networks": {"isolated": {"internal": True}}}
    write(ROOT / "compose.json", compose)
    command(["compose", "--project-name", PROJECT, "-f", str(ROOT / "compose.json"), "up", "-d", "--pull", "never"])
    verify_native()


def verify_native():
    wait_ready()
    info = json.loads(command(["inspect", PROJECT + "-seerr-1"]))[0]
    network = json.loads(command(["network", "inspect", PROJECT + "_isolated"]))[0]
    assert network["Internal"] and len(info["Mounts"]) == 2
    assert all(not value for value in info["NetworkSettings"]["Ports"].values())
    assert not any(m["Destination"] in {"/data", "/media", "/downloads", "/var/run/docker.sock"} for m in info["Mounts"])
    write(ROOT / "isolation.json", {"internal_network": True, "test_ca_only_inside_new_seerr": True,
        "official_pinned_seerr_image": images()["seerr"], "no_real_credentials_or_media_mounts": True,
        "synthetic_plex_account_service": True, "host_trust_unchanged": True})
    preserved()
    print("Isolated real Seerr ready; Plex identities/memberships are simulated over private TLS.", flush=True)


def wait_ready():
    with client() as probe:
        for _ in range(180):
            try:
                if probe.get("/api/v1/status").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.5)
    raise AssertionError("The isolated Seerr did not become ready")


def api(client, method, path, value=None, expected=200):
    response = client.request(method, "/api/v1" + path, **({"json": value} if value is not None else {}))
    assert response.status_code == expected, path + ": " + str(response.status_code)
    return response.json() if response.content else None


def client():
    return httpx.Client(base_url=ORIGIN, trust_env=False, timeout=30, transport=InternalHTTP())


def membership(shared=(9700102, 9700104), revoked=()):
    with httpx.Client(trust_env=False, timeout=10, transport=InternalHTTP()) as control:
        assert control.post(CONTROL + "/membership", json={"shared": list(shared), "revoked": list(revoked)}).status_code == 200


def admin():
    info = json.loads(command(["inspect", PROJECT + "-seerr-1"]))[0]
    settings = json.loads(command(["exec", info["Id"], "head", "-c", "131072", "/app/config/settings.json"]))
    result = client()
    result.headers["X-Api-Key"] = settings["main"]["apiKey"]
    return result


def native():
    accounts = read(ROOT / "fixture/access.json")["accounts"]
    with client() as owner:
        user = api(owner, "POST", "/auth/plex", {"authToken": accounts[0]["token"]})
        assert user["id"] == 1 and user["permissions"] == 2 and user["userType"] == 1
    with admin() as owner:
        api(owner, "POST", "/settings/plex", {"ip": "identity", "port": 32400, "useSsl": False})
        api(owner, "POST", "/settings/main", {"defaultPermissions": 32, "newPlexLogin": True, "localLogin": True})
        api(owner, "POST", "/settings/initialize")
        with client() as shared, client() as unshared:
            person = api(shared, "POST", "/auth/plex", {"authToken": accounts[1]["token"]})
            shared_id = person["id"]
            assert shared_id != 1 and person["permissions"] == 32 and person["userType"] == 1
            api(shared, "GET", "/settings/main", expected=403)
            api(shared, "POST", f"/user/{shared_id}/settings/permissions", {"permissions": 2}, expected=403)
            api(unshared, "POST", "/auth/plex", {"authToken": accounts[2]["token"]}, expected=403)
            assert len(api(owner, "GET", "/user")["results"]) == 2
            report("shared-user-admitted-with-request-only-defaults-and-unshared-denied", real_upstream_auth=True, external_membership_fixture=True)

            api(owner, "POST", "/settings/main", {"newPlexLogin": False})
            with client() as missing:
                api(missing, "POST", "/auth/plex", {"authToken": accounts[3]["token"]}, expected=403)
            imported = api(owner, "POST", "/user/import-from-plex", {"plexIds": [str(accounts[3]["id"])]}, expected=201)
            assert len(imported["createdUsers"]) == 1
            with client() as known:
                assert api(known, "POST", "/auth/plex", {"authToken": accounts[3]["token"]})["permissions"] == 32
            report("new-user-admission-disabled-but-explicit-import-can-sign-in", imported_user_scope_verified=True)

            membership(shared=(9700104,))
            with client() as retry:
                api(retry, "POST", "/auth/plex", {"authToken": accounts[1]["token"]}, expected=403)
            assert api(shared, "GET", "/auth/me")["id"] == shared_id
            api(owner, "DELETE", "/user/" + str(shared_id))
            api(shared, "GET", "/auth/me", expected=403)
            with client() as retry:
                api(retry, "POST", "/auth/plex", {"authToken": accounts[1]["token"]}, expected=403)
            report("share-revocation-denies-new-login-and-seerr-deletion-revokes-live-session", existing_session_survives_share_revocation=True,
                   complete_revocation_requires_seerr_user_removal=True)

            membership()
            api(owner, "POST", "/settings/main", {"newPlexLogin": True})
            with client() as recreated:
                api(recreated, "POST", "/auth/plex", {"authToken": accounts[1]["token"]})
                retained = api(recreated, "GET", "/auth/me")
                api(owner, "DELETE", "/user/" + str(retained["id"]))
                api(recreated, "GET", "/auth/me", expected=403)
            with client() as recreated:
                assert api(recreated, "POST", "/auth/plex", {"authToken": accounts[1]["token"]})["permissions"] == 32
            report("deletion-alone-does-not-block-readmission-while-sharing-and-new-logins-remain-enabled", readmission_is_documented_boundary=True)

        local()
        with httpx.Client(trust_env=False, transport=InternalHTTP()) as control:
            state = control.get(CONTROL + "/state").json()
        assert state["events"]["accounts"] > 0 and state["events"]["memberships"] > 0
        write(ROOT / "fixture-events.json", state["events"])
    preserved()


def local():
    with admin() as owner:
        if not (ROOT / "local-access-private.json").exists():
            invited_password = secrets.token_urlsafe(32)
            invited = api(owner, "POST", "/user", {"email": "invited-local@example.invalid", "username": "Invited local test", "password": invited_password}, expected=201)
            manager_password = secrets.token_urlsafe(32)
            manager = api(owner, "POST", "/user", {"email": "manager-local@example.invalid", "username": "Manager test", "password": manager_password}, expected=201)
            api(owner, "PUT", "/user/" + str(manager["id"]), {"username": "Manager test", "permissions": 8})
            write(ROOT / "local-access-private.json", {"invited": {"id": invited["id"], "password": invited_password}, "manager": {"id": manager["id"], "password": manager_password}})
        saved = read(ROOT / "local-access-private.json")
        invited, manager = saved["invited"], saved["manager"]
        invited_password, manager_password = invited["password"], manager["password"]
        with client() as guest, client() as steward:
            assert api(guest, "POST", "/auth/local", {"email": "invited-local@example.invalid", "password": invited_password})["id"] == invited["id"]
            api(steward, "POST", "/auth/local", {"email": "manager-local@example.invalid", "password": manager_password})
            api(guest, "GET", "/settings/main", expected=403)
            api(guest, "POST", "/user", {"email": "forbidden@example.invalid", "password": secrets.token_urlsafe(32)}, expected=403)
            api(guest, "DELETE", "/user/1", expected=403)
            api(guest, "GET", f"/user/{manager['id']}/settings/notifications", expected=403)
            api(steward, "POST", f"/user/{manager['id']}/settings/permissions", {"permissions": 2}, expected=403)
            api(steward, "PUT", f"/user/{invited['id']}", {"username": "Invited local test", "permissions": 2}, expected=403)
            api(owner, "DELETE", "/user/1", expected=405)
            report("invited-local-user-and-manager-cannot-grant-admin-or-change-owner", actual_session_cookies=True, no_invitation_email_sent=True)

            api(owner, "PUT", f"/user/{invited['id']}", {"username": "Invited local test", "permissions": 8})
            assert api(guest, "GET", "/auth/me")["permissions"] == 8
            api(guest, "GET", f"/user/{manager['id']}/settings/permissions")
            api(owner, "PUT", f"/user/{invited['id']}", {"username": "Invited local test", "permissions": 32})
            api(guest, "GET", f"/user/{manager['id']}/settings/permissions", expected=403)
            assert api(guest, "GET", "/auth/me")["permissions"] == 32
            report("permission-downgrade-takes-effect-on-already-open-session", no_cookie_reset_required=True)

            # NONE removes capabilities, not the ability to sign in.
            api(owner, "PUT", f"/user/{invited['id']}", {"username": "Invited local test", "permissions": 0})
            assert api(guest, "GET", "/auth/me")["permissions"] == 0
            with client() as retry:
                api(retry, "POST", "/auth/local", {"email": "invited-local@example.invalid", "password": invited_password})
            api(owner, "DELETE", "/user/" + str(invited["id"]))
            api(guest, "GET", "/auth/me", expected=403)
            with client() as retry:
                api(retry, "POST", "/auth/local", {"email": "invited-local@example.invalid", "password": invited_password}, expected=403)
            report("no-permissions-is-not-account-revocation-but-deletion-blocks-session-and-password-login")


def sql(statement, parameters=()):
    code = "const s=require('sqlite3');const db=new s.Database('/app/config/db/db.sqlite3');db.configure('busyTimeout',10000);db.all(" + json.dumps(statement) + "," + json.dumps(parameters) + ",(e,r)=>{if(e){process.exitCode=1;}else{console.log(JSON.stringify(r));}db.close();});"
    return json.loads(command(["exec", PROJECT + "-seerr-1", "node", "-e", code]))


def boundaries():
    with admin() as owner:
        identities = []
        for name in ("reader-a", "reader-b", "nonowner-admin"):
            password = secrets.token_urlsafe(32)
            created = api(owner, "POST", "/user", {"email": name + "@example.invalid", "username": name, "password": password}, expected=201)
            identities.append({"id": created["id"], "name": name, "password": password})
        write(ROOT / "boundary-access-private.json", identities)
        first, second, delegated_admin = identities
        # Synthetic pending records bypass metadata/download workflows entirely.
        for number, person in enumerate((first, second), 9700201):
            sql("INSERT INTO media (id,mediaType,tmdbId,status) VALUES (?,'movie',?,1)", [number, number])
            sql("INSERT INTO media_request (id,status,type,mediaId,requestedById,is4k,isAutoRequest,ignoreQuota) VALUES (?,1,'movie',?,?,0,0,0)", [number, number, person["id"]])
        with client() as reader:
            api(reader, "POST", "/auth/local", {"email": first["name"] + "@example.invalid", "password": first["password"]})
            assert [r["id"] for r in api(reader, "GET", "/request?filter=all")["results"]] == [9700201]
            api(reader, "GET", "/request/9700201")
            api(reader, "GET", "/request/9700202", expected=403)
            api(reader, "GET", "/request?requestedBy=" + str(second["id"]), expected=403)
            api(reader, "POST", "/request/9700202/approve", {}, expected=403)
            forged = reader.get("/api/v1/settings/main", headers={"X-API-User": "1"})
            assert forged.status_code == 403
            listing = api(reader, "GET", "/user")["results"]
            assert all(not ({"email", "plexId", "plexToken", "password", "settings"} & set(row)) for row in listing)
            api(owner, "PUT", "/user/" + str(first["id"]), {"username": first["name"], "permissions": 32 | 16384})
            assert {r["id"] for r in api(reader, "GET", "/request?filter=all")["results"]} == {9700201, 9700202}
            api(owner, "PUT", "/user/" + str(first["id"]), {"username": first["name"], "permissions": 32})
            api(reader, "GET", "/request/9700202", expected=403)
            assert [r["id"] for r in api(reader, "GET", "/request?filter=all")["results"]] == [9700201]
            assert sql("SELECT id,status FROM media_request ORDER BY id") == [{"id": 9700201, "status": 1}, {"id": 9700202, "status": 1}]
        report("request-ownership-private-profile-data-and-live-view-permission-downgrade", pending_records_only=True, no_download_requests=True)

        audit_admin_routes()


def audit_admin_routes():
    with admin() as owner:
        _, _, delegated_admin = read(ROOT / "boundary-access-private.json")
        # Exercise documented admin-account protection on alternate user routes.
        api(owner, "PUT", "/user/" + str(delegated_admin["id"]), {"username": delegated_admin["name"], "permissions": 2})
        manager = read(ROOT / "local-access-private.json")["manager"]
        with client() as steward:
            api(steward, "POST", "/auth/local", {"email": "manager-local@example.invalid", "password": manager["password"]})
            api(steward, "DELETE", "/user/" + str(delegated_admin["id"]), expected=405)
            changed = steward.put("/api/v1/user/" + str(delegated_admin["id"]), json={"username": delegated_admin["name"], "permissions": 32})
            assert changed.status_code in {200, 403}
            single = changed.status_code
            api(owner, "PUT", "/user/" + str(delegated_admin["id"]), {"username": delegated_admin["name"], "permissions": 2})
            changed = steward.put("/api/v1/user", json={"ids": [delegated_admin["id"]], "permissions": 32})
            assert changed.status_code in {200, 403}
            batch = changed.status_code
            api(owner, "PUT", "/user/" + str(delegated_admin["id"]), {"username": delegated_admin["name"], "permissions": 2})
        findings = []
        if single == 200 or batch == 200:
            findings.append({"id": "manage-users-can-downgrade-another-admin", "single_route_status": single,
                "batch_route_status": batch, "owner_unchanged": True, "ordinary_users_cannot_reach_routes": True,
                "guidance": "Grant Manage Users only to trusted administrators; delegated-admin protection needs an upstream fix."})
        write(ROOT / "findings.json", {"findings": findings, "upstream_image_unmodified": True})
        report("delegated-admin-alternate-route-protection-audited", observations_in_findings_report=True,
               delegated_admin_protection_passed=not findings)

        accounts = read(ROOT / "fixture/access.json")["accounts"]
        with client() as existing:
            user = api(existing, "POST", "/auth/plex", {"authToken": accounts[3]["token"]})
            membership(revoked=(9700104,))
            with client() as retry:
                api(retry, "POST", "/auth/plex", {"authToken": accounts[3]["token"]}, expected=500)
            assert api(existing, "GET", "/auth/me")["id"] == user["id"]
            api(owner, "DELETE", "/user/" + str(user["id"]))
            api(existing, "GET", "/auth/me", expected=403)
        membership()
        report("revoked-plex-authorization-denies-new-login-existing-session-needs-seerr-revocation", external_revocation_simulated=True)
        with httpx.Client(trust_env=False, transport=InternalHTTP()) as control:
            write(ROOT / "fixture-events.json", control.get(CONTROL + "/state").json()["events"])


def stop_native():
    before = set(command(["volume", "ls", "-q"]).split())
    command(["compose", "--project-name", PROJECT, "-f", str(ROOT / "compose.json"), "down"])
    assert before == set(command(["volume", "ls", "-q"]).split())
    preserved()
    write(ROOT / "native-cleaned.json", {"containers_network_removed": True, "config_volume_fixture_state_and_keys_retained": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "verify_native", "native", "local", "boundaries", "audit_admin_routes", "stop_native"])
    globals()[parser.parse_args().phase]()
