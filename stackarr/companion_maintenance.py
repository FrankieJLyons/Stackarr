"""Read-only companion release and saved-configuration checkpoints."""

import asyncio
import json

import httpx

from .companions import CLEANUP_JOBS
from .integrations import bounded_response
from .kuma import Kuma


def kuma_checkpoint(base, secret):
    with Kuma(base) as socket:
        socket.login(secret)
        fields = ("id", "name", "type", "hostname", "port", "url", "method", "body", "headers",
                  "interval", "retryInterval", "maxretries", "active", "upsideDown", "notificationIDList",
                  "accepted_statuscodes", "timeout", "authMethod", "basic_auth_user", "basic_auth_pass")
        monitors = sorted(({name: row.get(name) for name in fields} for row in socket.monitors()), key=lambda row: row["id"])
        socket.call("getAPIKeyList")
        keys = sorted(({name: row.get(name) for name in ("id", "name", "active", "expires")}
                       for row in socket.events.get("apiKeyList", [[]])[0]), key=lambda row: row["id"])
        return {"version": socket.events["info"][0]["version"], "monitors": monitors, "keys": keys}


async def request(base, secret, path, params=None):
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10,
                                headers={"X-Api-Key": secret.get("api_key", ""), "Accept": "application/json"}) as client:
        response, body = await bounded_response(client, "GET", base + path, params=params)
        response.raise_for_status()
        return json.loads(body)


async def version(key, base, secret):
    if key == "kuma":
        return (await asyncio.to_thread(kuma_checkpoint, base, secret))["version"]
    if key == "tautulli":
        data = await request(base, secret, "/api/v2", {"cmd": "get_tautulli_info"})
        return data["response"]["data"]["tautulli_version"]
    value = (await request(base, secret, "/api/status"))["application"]["version"]
    return value.removesuffix(".0") if len(value.split(".")) == 4 else value


async def checkpoint(key, base, secret):
    if key == "kuma":
        value = await asyncio.to_thread(kuma_checkpoint, base, secret)
        return {name: value[name] for name in ("monitors", "keys")}
    if key == "tautulli":
        data = (await request(base, secret, "/api/v2", {"cmd": "get_server_info"}))["response"]["data"]
        return {name: data.get(name) for name in ("pms_identifier", "pms_ip", "pms_port", "pms_url")}
    # Preserve the complete configuration, including credentials, privately in
    # the encrypted operation journal. Never expose it in the public review.
    value = {name: await request(base, secret, "/api/configuration/" + name)
             for name in ("general", *CLEANUP_JOBS, "sonarr", "radarr", "download_client")}
    # Reviewed 2.10.11 introduces this inactive queue option. Compare its exact
    # harmless default with absence on 2.10.10; any enabled threshold/deletion
    # option still changes the checkpoint and rejects the update.
    value["queue_cleaner"].setdefault("errored", {"maxStrikes": 0, "ignorePrivate": False,
                                                "deletePrivate": False, "changeCategory": False})
    return value
