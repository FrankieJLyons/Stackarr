"""Generated web logins for receipt-verified, initially unconfigured Arr apps."""

import json
import secrets

import httpx

from .adapters import require_write
from .bootstrap import BootstrapError
from .deployment_check import differences, inspect_container
from .docker_names import app_project

ARR = {"sonarr", "radarr", "prowlarr"}


def initialize(store):
    with store.db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS deployment_logins (
            id TEXT, app TEXT, value BLOB, PRIMARY KEY(id,app))""")


def verified_login(base, login, transport=None):
    # Use the app's normal forms login with a fresh cookie jar, never its API key.
    with httpx.Client(timeout=8, trust_env=False, follow_redirects=False, transport=transport) as client:
        response = client.post(base + "/login", data={"username": login["username"], "password": login["password"]})
        location = response.headers.get("location", "")
        if response.status_code not in (302, 303) or "login" in location.lower() or not client.cookies:
            return False
        response = client.get(base + "/")
        return response.status_code == 200


def read(deployments, identity, payload, key, api_key, transport=None):
    if key not in ARR or key not in payload["apps"]:
        raise ValueError("Choose an owned Arr app.")
    initialize(deployments.store)
    service = payload["compose"]["services"][key]
    info = inspect_container(deployments, identity, payload, key)
    if (differences(info, app_project(identity, payload), key, service)
            or not info.get("State", {}).get("Running") or info.get("State", {}).get("Paused")):
        raise ValueError("The app identity changed.")
    with deployments.store.db() as db:
        row = db.execute("SELECT value FROM deployment_logins WHERE id=? AND app=?", (identity, key)).fetchone()
    if not row:
        return None
    login = json.loads(deployments.store.cipher.decrypt(row[0]))
    if login["api_key"] != api_key:
        return None
    port = int(service["ports"][0]["published"])
    base = f"http://127.0.0.1:{port}"
    if not verified_login(base, login, transport):
        return None
    return {name: login[name] for name in ("username", "password")}


def prepare(deployments, identity, payload, credentials, transport=None):
    initialize(deployments.store)
    result = {}
    for key in payload["apps"]:
        if key not in ARR:
            continue
        require_write(key, "initial-login.create")
        service = payload["compose"]["services"][key]
        info = inspect_container(deployments, identity, payload, key)
        if (differences(info, app_project(identity, payload), key, service)
                or not info.get("State", {}).get("Running") or info.get("State", {}).get("Paused")
                or info.get("State", {}).get("Restarting")):
            raise BootstrapError("The installed app changed. Its existing login is preserved.")
        port = int(service["ports"][0]["published"])
        base = f"http://127.0.0.1:{port}"
        api_key = credentials[key]["api_key"]
        with deployments.store.db() as db:
            row = db.execute("SELECT value FROM deployment_logins WHERE id=? AND app=?", (identity, key)).fetchone()
        login = json.loads(deployments.store.cipher.decrypt(row[0])) if row else None
        if login and login["api_key"] != api_key:
            raise BootstrapError("The installed app credential changed. Its existing login is preserved.")
        version = "v1" if key == "prowlarr" else "v3"
        endpoint = base + f"/api/{version}/config/host"
        try:
            with httpx.Client(timeout=10, trust_env=False, follow_redirects=False, transport=transport,
                              headers={"X-Api-Key": api_key}) as client:
                response = client.get(endpoint)
                response.raise_for_status()
                host = response.json()
                if not isinstance(host, dict) or host.get("apiKey") != api_key or host.get("id") != 1:
                    raise BootstrapError("The app identity could not be confirmed for login setup.")
                if host.get("authenticationMethod") != "none" or host.get("username"):
                    ready = (login and host.get("authenticationMethod") == "forms"
                             and host.get("authenticationRequired") == "enabled"
                             and host.get("username") == login["username"]
                             and verified_login(base, login, transport))
                    result[key] = {"port": port, "api_key": api_key, "state": "ready" if ready else "existing",
                                   "login": {name: login[name] for name in ("username", "password")} if ready else None}
                    continue
                if host.get("password"):
                    raise BootstrapError("This app already has account details. They are preserved.")
                if not login:
                    login = {"api_key": api_key, "username": "stackarr", "password": secrets.token_urlsafe(32)}
                    with deployments.store.db() as db:
                        db.execute("INSERT INTO deployment_logins VALUES(?,?,?)", (identity, key,
                            deployments.store.cipher.encrypt(json.dumps(login).encode())))
                # Keep the complete advertised host resource, including upstream secret placeholders.
                # Check it again immediately before the one fixed write; preserve later app edits.
                response = client.get(endpoint)
                response.raise_for_status()
                if response.json() != host:
                    raise BootstrapError("App settings changed during login setup. Review them before trying again.")
                updated = {**host, "authenticationMethod": "forms", "authenticationRequired": "enabled",
                           "username": login["username"], "password": login["password"], "passwordConfirmation": login["password"]}
                response = client.put(endpoint + "/1", json=updated)
                response.raise_for_status()
            if not verified_login(base, login, transport):
                raise BootstrapError("The generated app login could not be verified. Its saved checkpoint is retained; retry after the app is ready.")
            result[key] = {"port": port, "api_key": api_key, "state": "ready",
                           "login": {name: login[name] for name in ("username", "password")}}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, BootstrapError):
                raise
            raise BootstrapError("App login setup could not finish. Its saved checkpoint is retained; check the app and retry.") from None
    return {"id": identity, "apps": result}
