"""Isolated real HTTP regression matrix for the packaged Seerr security backport."""

import argparse
import base64
import inspect
import json
import secrets
import subprocess
import threading
from pathlib import Path

import httpx

from stackarr.docker_runtime import executable
from stackarr.self_update import write
from tools import docker_seerr_permissions_check as lab

ROOT = Path("test-results/docker-seerr-permissions-fix-20261019-r1").resolve()
lab.ROOT = ROOT / "native-final"
lab.PROJECT = "stackarr-seerr-permissions-fix-20261019-r2"

BRIDGE = """import base64,json,sys,httpx
for line in sys.stdin:
 try:
  r=json.loads(line)
  assert r['url'].startswith(('http://seerr:5055/','http://identity:8888/'))
  with httpx.Client(trust_env=False,timeout=20) as c:
   response=c.request(r['method'],r['url'],headers=r['headers'],content=base64.b64decode(r['body']))
   print(json.dumps({'status':response.status_code,'headers':response.headers.multi_items(),'body':base64.b64encode(response.content).decode()}),flush=True)
 except Exception:
  print(json.dumps({'error':True}),flush=True)
"""


class PersistentHTTP(httpx.BaseTransport):
    worker = None
    lock = threading.Lock()

    def handle_request(self, request):
        with self.lock:
            if self.__class__.worker is None:
                self.__class__.worker = subprocess.Popen([executable(), "exec", "-i", lab.PROJECT + "-identity-1", "python", "-u", "-c", BRIDGE],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            worker = self.__class__.worker
            worker.stdin.write(json.dumps({"method": request.method, "url": str(request.url), "headers": list(request.headers.multi_items()),
                "body": base64.b64encode(request.read()).decode()}) + "\n")
            worker.stdin.flush()
            reply = json.loads(worker.stdout.readline())
            if reply.get("error"):
                raise httpx.ConnectError("Isolated HTTP request failed")
            return httpx.Response(reply["status"], headers=reply["headers"], content=base64.b64decode(reply["body"]))

    @classmethod
    def finish(cls):
        if cls.worker:
            cls.worker.stdin.close()
            cls.worker.wait(timeout=30)
            cls.worker = None


lab.InternalHTTP = PersistentHTTP


def matrix():
    with lab.admin() as owner:
        people = {}
        for name, permissions in (("manager", 40), ("admin", 2), ("guest", 32), ("second", 32), ("settings", 4)):
            password = secrets.token_urlsafe(32)
            user = lab.api(owner, "POST", "/user", {"email": name + "-fix@example.invalid", "username": name, "password": password}, expected=201)
            lab.api(owner, "PUT", f"/user/{user['id']}", {"username": name, "permissions": permissions})
            people[name] = {"id": user["id"], "password": password, "permissions": permissions}
        write(lab.ROOT / "matrix-private.json", people)
        results = fast_matrix(owner.headers["X-Api-Key"], people)
        write(lab.ROOT / "matrix-result.json", {"passed": True, "checks": results})


def fast_matrix(key, people):
    # One Docker exec, then normal real HTTP for every check inside the internal
    # network. This avoids a new Docker CLI process for each API request.
    script = "import httpx,json,sys\nfrom types import SimpleNamespace\n" + inspect.getsource(lab.api)
    script += "\nlab=SimpleNamespace(api=api)\n" + inspect.getsource(exercise)
    script += "\nv=json.load(sys.stdin)\nwith httpx.Client(base_url='http://seerr:5055',trust_env=False,timeout=30,headers={'X-Api-Key':v['key']}) as owner:\n print(json.dumps(exercise(lambda:httpx.Client(base_url='http://seerr:5055',trust_env=False,timeout=30),owner,v['people'])))\n"
    result = subprocess.run([executable(), "exec", "-i", lab.PROJECT + "-identity-1", "python", "-c", script],
        input=json.dumps({"key": key, "people": people}), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, "Internal real HTTP matrix failed; private output withheld."
    return json.loads(result.stdout)


def exercise(client, owner, people):
    """Shared contract for native fixture and real packaged browser account session."""
    actor, administrator, guest, second = [people[name] for name in ("manager", "admin", "guest", "second")]
    protected_ids = (1, administrator["id"], actor["id"], people["settings"]["id"])
    results = []
    def route(target, mode, permissions):
        if mode == "single":
            return "PUT", f"/user/{target}", {"username": "permission-matrix", "permissions": permissions}
        if mode == "batch":
            return "PUT", "/user", {"ids": [target], "permissions": permissions}
        return "POST", f"/user/{target}/settings/permissions", {"permissions": permissions}
    def state():
        return {u["id"]: (u["username"], u["permissions"]) for u in lab.api(owner, "GET", "/user?take=100")["results"]}
    with client() as manager:
        lab.api(manager, "POST", "/auth/local", {"email": "manager-fix@example.invalid", "password": actor["password"]})
        for mode in ("single", "batch", "settings"):
            for target in protected_ids:
                before = state()
                lab.api(manager, *route(target, mode, 32), expected=403)
                assert state() == before
                results.append(mode + "-protect-" + str(target))
            for permissions in (2, 4, 16):
                before = state()
                lab.api(manager, *route(guest["id"], mode, permissions), expected=403)
                assert state() == before
                results.append(mode + "-deny-escalation-" + str(permissions))
            lab.api(manager, *route(guest["id"], mode, 0))
            assert state()[guest["id"]][1] == 0
            lab.api(manager, *route(guest["id"], mode, 32))
            results.append(mode + "-ordinary-user-edit-allowed")
            lab.api(owner, *route(administrator["id"], mode, 32))
            lab.api(owner, *route(administrator["id"], mode, 2))
            lab.api(owner, *route(1, mode, 0), expected=403)
            results.append(mode + "-owner-can-edit-other-admin-but-not-demote-self")
        for protected in protected_ids:
            for ids in ([guest["id"], protected, second["id"]], [protected, guest["id"]]):
                before = state()
                lab.api(manager, "PUT", "/user", {"ids": ids, "permissions": 0}, expected=403)
                assert state() == before
                results.append("atomic-mixed-batch-" + str(ids))
        before = state()
        lab.api(manager, "PUT", "/user", {"ids": [guest["id"], 999999], "permissions": 0}, expected=404)
        assert state() == before
        lab.api(manager, "PUT", "/user", {"ids": [guest["id"], guest["id"], second["id"]], "permissions": 0})
        assert state()[guest["id"]][1] == state()[second["id"]][1] == 0
        lab.api(owner, "PUT", "/user", {"ids": [guest["id"], second["id"]], "permissions": 32})
        results.extend(["unknown-target-batch-no-partial-write", "duplicate-valid-batch-atomic"])
        for target in (1, administrator["id"], people["settings"]["id"]):
            lab.api(manager, "POST", f"/user/{target}/settings/main", {"username": "forbidden", "email": "forbidden@example.invalid"}, expected=403)
        lab.api(manager, "POST", f"/user/{actor['id']}/settings/main", {"username": "manager", "email": "manager-fix@example.invalid"})
        results.append("protected-profile-email-and-manager-own-profile")
        lab.api(manager, "DELETE", f"/user/{administrator['id']}", expected=405)
        lab.api(owner, "PUT", f"/user/{actor['id']}", {"permissions": 32})
        lab.api(manager, "PUT", f"/user/{guest['id']}", {"permissions": 0}, expected=403)
        lab.api(owner, "PUT", f"/user/{actor['id']}", {"permissions": 40})
        results.append("live-manager-revocation-with-existing-cookie")
    with client() as admin:
        lab.api(admin, "POST", "/auth/local", {"email": "admin-fix@example.invalid", "password": administrator["password"]})
        lab.api(admin, "PUT", f"/user/{guest['id']}", {"permissions": 2}, expected=403)
        lab.api(admin, "PUT", f"/user/{guest['id']}", {"permissions": 16384})
        lab.api(owner, "PUT", f"/user/{guest['id']}", {"permissions": 32})
        results.append("nonowner-admin-cannot-grant-admin-but-can-manage-ordinary-user")
    return results


def run():
    lab.ROOT.mkdir(exist_ok=True)
    lab.prepare()
    isolation = json.loads((lab.ROOT / "isolation.json").read_text())
    isolation["security_backport_image"] = isolation.pop("official_pinned_seerr_image")
    write(lab.ROOT / "isolation.json", isolation)
    lab.native()
    # Keep the previous request/privacy regressions, replacing its audit-only check.
    lab.audit_admin_routes = lambda: None
    lab.boundaries()
    matrix()
    lab.report("security-backport-all-mutation-routes-and-atomic-batches", delegated_admin_protection_passed=True)
    PersistentHTTP.finish()
    lab.stop_native()
    write(ROOT / "native-result.json", {"passed": True, "image": lab.images()["seerr"], "real_http": True,
        "external_plex_identity_simulated": True, "no_media_mounted": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["run", "matrix", "stop"])
    phase = parser.parse_args().phase
    if phase == "run":
        run()
    elif phase == "matrix":
        matrix()
    else:
        lab.stop_native()
