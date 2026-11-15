"""Owned-app credential handoff from an enrolled controller to the dashboard only."""

import json
import re

from .config import CATALOG, Config
from .integrations import IntegrationError, collect
from .store import Conflict, initialize_connection_progress

CORE = {"sonarr", "radarr", "prowlarr", "qbittorrent"}
COMPANIONS = {"tautulli", "kuma", "cleanuparr"}
ACCOUNT_APPS = {"plex", "seerr"} | COMPANIONS
SUPPORTED = CORE | ACCOUNT_APPS


def refresh_ports(store, operations):
    """Reconcile a lost approval response using only trusted host status and a
    previously reviewed, unactivated dashboard binding. Saved apps stay intact.
    """
    with store.db() as db:
        for operation in operations:
            ports = operation.get("ports")
            if (not operation.get("port_recovery") or not isinstance(ports, dict) or not ports
                    or set(ports) != set(operation.get("apps", [])) or set(ports) - SUPPORTED
                    or any(not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535 for port in ports.values())):
                continue
            row = db.execute("SELECT ports,activated FROM controller_connections WHERE id=?", (operation["id"],)).fetchone()
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='connection_progress'").fetchone()
            started = db.execute("SELECT 1 FROM connection_progress WHERE deployment=? AND receipt IS NOT NULL", (operation['id'],)).fetchone() if table else None
            if row and not row[1] and not started and set(json.loads(row[0])) == set(ports):
                db.execute("UPDATE controller_connections SET ports=? WHERE id=? AND activated=0", (json.dumps(ports), operation["id"]))


def binding(store, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Choose an installation reviewed in this dashboard.")
    with store.db() as db:
        row = db.execute("SELECT revision,ports,activated FROM controller_connections WHERE id=?", (identity,)).fetchone()
    if not row:
        raise ValueError("Choose an installation reviewed in this dashboard.")
    ports = {key: port for key, port in json.loads(row[1]).items() if key in SUPPORTED}
    if not ports or any(type(port) is not int or not 1 <= port <= 65535 for port in ports.values()):
        raise ValueError("This installation has no supported app connections.")
    return row[0], ports, row[2]


def validate_candidate(key, candidate):
    if key in ACCOUNT_APPS and candidate is None:
        return
    fields = {"username", "password"} if key == "qbittorrent" else {"api_key"}
    if not isinstance(candidate, dict) or set(candidate) != fields:
        raise ValueError("Unsupported app credential")
    if key == "qbittorrent":
        valid = candidate["username"] == "admin" and isinstance(candidate["password"], str) and re.fullmatch(
            r"[\x21-\x7e]{8,512}", candidate["password"])
    else:
        pattern = r"[\x21-\x7e]{8,512}" if key in ACCOUNT_APPS else r"[a-fA-F0-9]{32}"
        valid = isinstance(candidate["api_key"], str) and re.fullmatch(pattern, candidate["api_key"])
    if not valid:
        raise ValueError("Unsupported app credential")


async def candidates(controller, identity, ports):
    result = {}
    selected = set(ports) & CORE
    if selected:
        reply = await controller.request("app-connections", {"id": identity})
        if (not isinstance(reply, dict) or set(reply) != {"id", "apps"} or reply["id"] != identity
                or not isinstance(reply["apps"], dict) or set(reply["apps"]) != selected):
            raise ValueError("Installed app identities changed")
        for key, app in reply["apps"].items():
            if (not isinstance(app, dict) or set(app) != {"port", "credential"}
                    or type(app["port"]) is not int or app["port"] != ports[key]):
                raise ValueError("Installed app port changed")
            result[key] = app["credential"]
    selected = COMPANIONS & set(ports)
    if selected:
        reply = await controller.request("companion-connections", {"id": identity})
        if (not isinstance(reply, dict) or set(reply) != {"id", "apps"} or reply["id"] != identity
                or not isinstance(reply["apps"], dict) or set(reply["apps"]) != selected):
            raise ValueError("Companion installation identities changed")
        for key, app in reply["apps"].items():
            if not isinstance(app, dict) or set(app) != {"port", "credential"} or type(app["port"]) is not int or app["port"] != ports[key]:
                raise ValueError("Companion port changed")
            result[key] = app["credential"]
    for key in {"plex", "seerr"} & set(ports):
        reply = await controller.request(key + "-connection", {"id": identity})
        if (not isinstance(reply, dict) or set(reply) != {"id", "port", "credential"} or reply["id"] != identity
                or type(reply["port"]) is not int or reply["port"] != ports[key]):
            raise ValueError("Account app installation identity changed")
        result[key] = reply["credential"]
    for key, credential in result.items():
        validate_candidate(key, credential)
    return result


def connected_apps(store, identity):
    """Only unchanged, privately receipted connections count as completed."""
    _, ports, activated = binding(store, identity)
    config = store.config()[1]
    with store.db() as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE name='connection_progress'").fetchone()
        receipts = dict(db.execute('SELECT app,receipt FROM connection_progress WHERE deployment=? AND receipt IS NOT NULL', (identity,))) if table else {}
    result = set()
    for key, port in ports.items():
        app = config.integrations[key]
        if app.read_only or not app.enabled or app.url != f'http://host.docker.internal:{port}':
            continue
        if key in receipts:
            saved = json.loads(store.cipher.decrypt(receipts[key]))
            if saved == {'integration': app.model_dump(), 'credential': store.secret(key)}:
                result.add(key)
        elif activated and store.secret(key):  # Compatibility with completed older installations.
            result.add(key)
    return result


def progress(store, identity):
    _, ports, _ = binding(store, identity)
    ready = connected_apps(store, identity)
    with store.db() as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE name='connection_progress'").fetchone()
        saved = {row[0]: row[1:] for row in db.execute(
            'SELECT app,state,detail FROM connection_progress WHERE deployment=?', (identity,))} if table else {}
    rows = []
    for key in ports:
        state, detail = saved.get(key, ('pending', 'Choose Finish connecting to check this app.'))
        if key in ready:
            state, detail = 'saved', 'Connected. Connection details are saved privately.'
        elif state in {'saved', 'connected'}:
            state, detail = 'changed', 'This connection changed. Your current settings are preserved.'
        rows.append(dict(app=key, name=CATALOG[key]['name'], state=state, detail=detail))
    return rows


async def finish_owned(store, controller, identity, transport=None):
    _, ports, activated = binding(store, identity)
    revision, config = store.config()

    def rows(state, detail, keys=None):
        return {"apps": [{"app": key, "name": CATALOG[key]["name"], "state": state, "detail": detail}
                         for key in ports if keys is None or key in keys]}

    if activated:
        return rows("saved", "Connection details are already saved. Use Test saved connections to check them.",
                    {key for key in ports if config.integrations[key].enabled})
    completed = connected_apps(store, identity)
    result = progress(store, identity)
    eligible = set()
    for row in result:
        key = row['app']
        if key in completed:
            continue
        app = config.integrations[key]
        if app.enabled or app.url or app.read_only or store.secret(key):
            row.update(state='changed', detail='An existing connection is preserved. Review it in Apps; this installation will not replace it.')
        else:
            eligible.add(key)
    with store.db() as db:
        # Earlier installations did not record a quality preference.
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='controller_quality_profiles'").fetchone()
        row = db.execute("SELECT profiles FROM controller_quality_profiles WHERE id=?", (identity,)).fetchone() if table else None
    profiles = json.loads(row[0]) if row else {}
    from .quality import LABELS

    if (not isinstance(profiles, dict) or set(profiles) - (set(ports) & {"sonarr", "radarr"})
            or any(profile not in LABELS for profile in profiles.values())):
        raise ValueError("The reviewed request quality preferences changed")
    # Validate the complete private handoff before saving any of it.
    credentials = await candidates(controller, identity, ports) if eligible else {}
    ready = {}
    for row in result:
        key = row['app']
        if key not in eligible:
            continue
        if credentials[key] is None:
            row.update(state='needs-setup', detail=('Review companion setup below, then retry this check.' if key in COMPANIONS else
                       f'Open {CATALOG[key]["name"]}, sign in and finish its setup, then retry. Other ready apps can connect now.'))
            continue
        port = ports[key]
        app = config.integrations[key]
        # Docker Desktop's host route also connects apps installed in later batches.
        address = f"http://host.docker.internal:{port}"
        app.enabled, app.mode, app.url, app.peer_url, app.port = True, "connect", address, address, port
        app.browser_url = f"http://localhost:{port}" + ("/web" if key == "plex" else "")
        app.quality_profile = profiles.get(key, "")
        try:
            await collect(key, app, credentials[key], transport)
        except IntegrationError:
            config.integrations[key] = store.config()[1].integrations[key]
            row.update(state='waiting', detail='This app is not reachable from Stackarr yet. Check it, then retry; other ready apps are saved.')
        else:
            ready[key] = credentials[key]
            row.update(state='connected', detail='Connected to Stackarr. Connection details were saved privately.')
    try:
        if ready:
            store.save(Config.model_validate(config.model_dump()), revision, ready,
                       complete_controller=identity if completed | set(ready) == set(ports) else None,
                       connection_progress=(identity, result))
            for key in ready:
                store.audit('connection.finished', key)
        else:
            with store.db() as db:
                initialize_connection_progress(db)
                for row in result:
                    db.execute('''INSERT INTO connection_progress VALUES(?,?,?,?,NULL)
                        ON CONFLICT(deployment,app) DO UPDATE SET state=excluded.state,detail=excluded.detail''',
                               (identity, row['app'], row['state'], row['detail']))
        return {'apps': result}
    except Conflict:
        return rows("changed", "Settings changed during this check. Your newer settings are preserved; review these apps in Apps.")


async def finish_plex(store, controller, identity, transport=None):
    """Compatibility entry point for the original packaged Plex slice."""
    return await finish_owned(store, controller, identity, transport)


async def generated_login(store, controller):
    saved = store.secret("qbittorrent")
    with store.db() as db:
        identities = [row[0] for row in db.execute("SELECT id FROM controller_connections")]
    for identity in identities:
        _, ports, _ = binding(store, identity)
        if 'qbittorrent' not in connected_apps(store, identity):
            continue
        owned = await candidates(controller, identity, ports)
        if saved and owned["qbittorrent"] == saved:
            return saved
    raise ValueError("No unchanged Stackarr-generated qBittorrent login is available.")


async def companion_login(store, controller, key):
    if key not in COMPANIONS:
        raise ValueError("Choose a generated companion login")
    saved = store.secret(key)
    with store.db() as db:
        identities = [row[0] for row in db.execute("SELECT id FROM controller_connections")]
    for identity in identities:
        _, ports, _ = binding(store, identity)
        if key not in connected_apps(store, identity):
            continue
        reply = await controller.request("companion-login", {"id": identity, "app": key})
        if (set(reply) != {"id", "app", "port", "api_key", "login"} or reply["id"] != identity or reply["app"] != key
                or reply["port"] != ports[key] or not saved or reply["api_key"] != saved["api_key"]
                or set(reply["login"]) != {"username", "password"} or reply["login"]["username"] != "stackarr"
                or not isinstance(reply["login"]["password"], str) or not 16 <= len(reply["login"]["password"]) <= 512):
            raise ValueError("The companion login or connection changed")
        return reply["login"]
    raise ValueError("No unchanged generated companion login is available")
