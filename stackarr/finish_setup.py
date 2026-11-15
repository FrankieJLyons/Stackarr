"""Connect freshly installed account-based apps without exposing their credentials."""

import asyncio
import json
import re
import xml.etree.ElementTree as ET

from .config import CATALOG
from .deployment import DeploymentError
from .deployment_check import differences, inspect_container, load_receipt
from .docker_names import app_project
from .integrations import IntegrationError, collect
from .store import Conflict

FILES = {
    "plex": "/config/Library/Application Support/Plex Media Server/Preferences.xml",
    "seerr": "/app/config/settings.json",
}
LIMIT = 131072


def read_settings(deployments, identity, payload, key, integration):
    """Private fixed-file read after receipt, connection and running-state checks."""
    service = payload["compose"]["services"][key]
    port = service["ports"][0]["published"]
    if not integration.enabled or integration.url != f"http://127.0.0.1:{port}":
        raise DeploymentError("The saved connection changed. Review this app in Apps before continuing.")
    info = inspect_container(deployments, identity, payload, key)
    if differences(info, app_project(identity, payload), key, service):
        raise DeploymentError("Installation settings changed. Check this installation in Apps before continuing.")
    runtime = info.get("State", {})
    if not runtime.get("Running") or runtime.get("Paused") or runtime.get("Restarting"):
        raise DeploymentError("Start this app and wait for it to be ready, then try again.")
    container = info.get("Id", "")
    if not re.fullmatch(r"[a-f0-9]{64}", container):
        raise DeploymentError("Could not confirm this installed app. Check its installation in Apps.")
    # Fixed file, bounded output, exact inspected container ID; never execute a shell.
    raw = deployments._call(["--context", payload["context"]["name"], "exec", container,
                             "head", "-c", str(LIMIT + 1), FILES[key]], timeout=5)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Oversized settings")
    return raw


def read_candidate(deployments, identity, payload, key, integration):
    raw = read_settings(deployments, identity, payload, key, integration)
    if key == "plex":
        if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
            raise ValueError("Unsupported XML")
        token = ET.fromstring(raw).attrib.get("PlexOnlineToken", "")
    else:
        settings = json.loads(raw)
        token = settings.get("main", {}).get("apiKey", "") if settings.get("public", {}).get("initialized") is True else ""
    if not token:
        return None
    if not isinstance(token, str) or not re.fullmatch(r"[\x21-\x7e]{8,512}", token):
        raise ValueError("Invalid credential")
    return {"api_key": token}


async def finish(deployments, identity, transport=None):
    payload = await asyncio.to_thread(load_receipt, deployments, identity)
    rows = []
    for key in payload["apps"]:
        if key not in FILES:
            continue
        revision, config = deployments.store.config()
        integration = config.integrations[key]
        if not integration.enabled:
            continue
        state, detail = "needs-setup", ""
        if deployments.store.secret(key):
            state, detail = "saved", "Connection details are already saved. Use Test saved connections to check them."
        else:
            try:
                candidate = await asyncio.to_thread(read_candidate, deployments, identity, payload, key, integration)
                if candidate is None:
                    detail = "Open this app and complete its account setup, then choose Finish connecting again."
                else:
                    await collect(key, integration, candidate, transport)
                    # Saving checks the revision transactionally, including credential edits.
                    deployments.store.save(config, revision, {key: candidate})
                    deployments.store.audit("connection.finished", key)
                    state, detail = "connected", "Connected to Stackarr. Your connection details were saved privately."
            except Conflict:
                state, detail = "changed", "Settings changed during this check. Try again using your saved settings."
            except IntegrationError:
                state, detail = "waiting", "This app is not ready to connect yet. Finish its setup and try again."
            except (DeploymentError, OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, ET.ParseError):
                state, detail = "check-needed", "Could not safely read this installed app. Check its installation in Apps, then try again."
        rows.append({"app": key, "name": CATALOG[key]["name"], "state": state, "detail": detail})
    return {"apps": rows}
