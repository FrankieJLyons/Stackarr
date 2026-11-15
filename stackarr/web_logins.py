"""Reviewed private Arr login handoff; ordinary browser responses contain no passwords."""

import json
import re

from .arr_logins import ARR
from .config import CATALOG
from .controller_connections import binding, connected_apps
from .store import Conflict


def initialize(store):
    with store.db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS app_logins (
            app TEXT PRIMARY KEY, deployment TEXT, port INTEGER, value BLOB)""")


def review(store, identity):
    _, ports, activated = binding(store, identity)
    revision, config = store.config()
    selected = {key: port for key, port in ports.items() if key in ARR}
    if not selected or not set(selected) <= connected_apps(store, identity):
        raise ValueError("Finish connecting this installation before preparing its logins.")
    keys = {}
    for key, port in selected.items():
        app = config.integrations[key]
        secret = store.secret(key).get("api_key")
        if not app.enabled or app.url != f"http://host.docker.internal:{port}" or not secret:
            raise ValueError("The saved app connection changed. Review it in Apps.")
        keys[key] = secret
    return {"id": identity, "revision": revision, "ports": selected, "keys": keys}


def public(plan):
    return {"apps": [{"app": key, "name": CATALOG[key]["name"]} for key in plan["ports"]],
            "notice": "Create and save a unique generated web login only where an installed app has no login yet. Existing logins are preserved. Stackarr verifies each generated login before saving it privately."}


async def apply(store, controller, plan):
    if review(store, plan["id"]) != plan:
        raise Conflict("Settings changed. Review app logins again.")
    reply = await controller.request("arr-logins", {"id": plan["id"]})
    if (not isinstance(reply, dict) or set(reply) != {"id", "apps"} or reply["id"] != plan["id"]
            or not isinstance(reply["apps"], dict) or set(reply["apps"]) != set(plan["ports"])):
        raise ValueError("The login handoff identity changed.")
    for key, value in reply["apps"].items():
        if (not isinstance(value, dict) or set(value) != {"port", "api_key", "state", "login"}
                or type(value["port"]) is not int or value["port"] != plan["ports"][key]
                or value["api_key"] != plan["keys"][key] or value["state"] not in {"ready", "existing"}):
            raise ValueError("The app login handoff changed.")
        login = value["login"]
        if value["state"] == "existing":
            if login is not None:
                raise ValueError("An existing login must stay private to its owner.")
        elif (not isinstance(login, dict) or set(login) != {"username", "password"} or login["username"] != "stackarr"
                or not isinstance(login["password"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", login["password"])):
            raise ValueError("Unsupported generated login.")
    initialize(store)
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT revision FROM settings WHERE id=1").fetchone()[0] != plan["revision"]:
            raise Conflict("Settings changed. Generated logins remain on the installation computer; review again to reconnect them.")
        for key, value in reply["apps"].items():
            existing = db.execute("SELECT deployment FROM app_logins WHERE app=?", (key,)).fetchone()
            if existing and existing[0] != plan["id"]:
                raise Conflict("An app login is already saved for a different installation.")
            if value["state"] == "ready":
                record = {**value["login"], "api_key": value["api_key"]}
                db.execute("INSERT OR REPLACE INTO app_logins VALUES(?,?,?,?)", (key, plan["id"], value["port"],
                           store.cipher.encrypt(json.dumps(record).encode())))
    store.audit("app-logins.prepared", plan["id"])
    return {"apps": [{"app": key, "name": CATALOG[key]["name"], "state": value["state"],
                      "detail": "Generated login saved privately." if value["state"] == "ready" else "Your existing login is preserved. Use the login you chose."}
                     for key, value in reply["apps"].items()]}


async def reveal(store, controller, key):
    if key not in ARR:
        raise ValueError("Choose an Arr app.")
    initialize(store)
    with store.db() as db:
        row = db.execute("SELECT deployment,port,value FROM app_logins WHERE app=?", (key,)).fetchone()
    if not row:
        raise ValueError("Prepare this app's generated login first.")
    identity, port, encrypted = row
    saved = json.loads(store.cipher.decrypt(encrypted))
    app = store.config()[1].integrations[key]
    if (not app.enabled or app.url != f"http://host.docker.internal:{port}"
            or store.secret(key).get("api_key") != saved["api_key"]):
        raise ValueError("This app's saved connection changed. Your current settings are preserved.")
    reply = await controller.request("arr-login", {"id": identity, "app": key})
    login = {name: saved[name] for name in ("username", "password")}
    if reply != {"id": identity, "app": key, "port": port, "api_key": saved["api_key"], "login": login}:
        raise ValueError("The app login changed. Use the credentials you chose in that app.")
    return login
