"""Credential handoff from newly owned containers only. Never probes existing apps."""

import json
import re
import secrets
import time
import xml.etree.ElementTree as ET

import httpx

from .adapters import require_write


class BootstrapError(ValueError):
    pass


def accepted(response):
    return response.status_code == 204 or (response.status_code == 200 and response.text.strip() == "Ok.")


def credentials(deployment, identity, payload):
    """Encrypted checkpoints preserve generated passwords across interrupted setup."""
    with deployment.store.db() as db:
        row = db.execute("SELECT value FROM deployment_secrets WHERE id=?", (identity,)).fetchone()
    saved = json.loads(deployment.store.cipher.decrypt(row[0])) if row else {}

    def checkpoint():
        encrypted = deployment.store.cipher.encrypt(json.dumps(saved).encode())
        with deployment.store.db() as db:
            db.execute("INSERT OR REPLACE INTO deployment_secrets VALUES(?,?)", (identity, encrypted))

    context = payload["context"]["name"]
    for key in payload["apps"]:
        if key not in ("sonarr", "radarr", "prowlarr", "qbittorrent"):
            continue
        container = deployment.owned_container(identity, payload, key)
        port = payload["compose"]["services"][key]["ports"][0]["published"]
        base = f"http://127.0.0.1:{port}"
        if key != "qbittorrent":
            # Config creation can lag behind a container reporting "running".
            for attempt in range(20):
                try:
                    xml = deployment._call(["--context", context, "exec", container, "cat", "/config/config.xml"])
                    if len(xml) > 131072:
                        raise BootstrapError("Unexpected app configuration size")
                    token = ET.fromstring(xml).findtext("ApiKey", "")
                    if not re.fullmatch(r"[a-fA-F0-9]{32}", token):
                        raise BootstrapError("App API key is not ready")
                    with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                        version = "v1" if key == "prowlarr" else "v3"
                        response = client.get(base + f"/api/{version}/system/status", headers={"X-Api-Key": token})
                        response.raise_for_status()
                        if not isinstance(response.json().get("version"), str):
                            raise BootstrapError("App identity could not be verified")
                    saved[key] = {"api_key": token}
                    checkpoint()
                    break
                except (ValueError, ET.ParseError, httpx.HTTPError):
                    if attempt == 19:
                        raise BootstrapError("An installed Arr app is not ready for credential handoff. Resume when it has started.") from None
                    time.sleep(1)
        else:
            first_attempt = key not in saved
            if first_attempt:
                saved[key] = {"username": "admin", "password": secrets.token_urlsafe(32)}
                checkpoint()  # Always durable before changing the upstream password.
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False, headers={"Referer": base}) as client:
                ready = False
                for attempt in range(20):
                    try:
                        response = client.get(base + "/")
                        ready = response.status_code == 200
                    except httpx.HTTPError:
                        pass
                    if ready:
                        break
                    time.sleep(1)
                if not ready:
                    raise BootstrapError("qBittorrent has not started yet. Resume after checking Docker.")
                logged_in = False
                if not first_attempt:
                    logged_in = accepted(client.post(base + "/api/v2/auth/login", data=saved[key]))
                if not logged_in:
                    logs = deployment._call(["--context", context, "logs", "--tail", "200", container])
                    temporary = re.findall(r"temporary password is provided for this session: (\S+)", logs)
                    if not temporary or not accepted(client.post(base + "/api/v2/auth/login", data={"username": "admin", "password": temporary[-1]})):
                        raise BootstrapError("qBittorrent credential handoff needs attention. No authentication settings were disabled.")
                    response = client.post(base + "/api/v2/app/setPreferences", data={"json": json.dumps({
                        "web_ui_password": saved[key]["password"], "save_path": "/data/downloads"})})
                    response.raise_for_status()
                # Verify the durable credential with a new cookie jar, not the bootstrap session.
            with httpx.Client(timeout=5, trust_env=False, headers={"Referer": base}) as client:
                if not accepted(client.post(base + "/api/v2/auth/login", data=saved[key])):
                    raise BootstrapError("The saved qBittorrent password could not be verified. Resume to recover.")
                client.get(base + "/api/v2/torrents/info").raise_for_status()
    return saved


def libraries(payload, saved):
    """Register the reviewed library paths only in freshly owned Arr applications."""
    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
        for key, path in (("sonarr", "/data/media/tv"), ("radarr", "/data/media/movies")):
            if key not in payload["apps"]:
                continue
            require_write(key, "root-folder.create")
            port = payload["compose"]["services"][key]["ports"][0]["published"]
            endpoint = f"http://127.0.0.1:{port}/api/v3/rootfolder"
            headers = {"X-Api-Key": saved[key]["api_key"]}
            try:
                response = client.get(endpoint, headers=headers)
                response.raise_for_status()
                existing = response.json()
                if any(row.get("path") == path for row in existing):
                    continue
                if existing:
                    raise BootstrapError("Library folders were changed in an installed app. Existing folders are preserved; review them before resuming.")
                response = client.post(endpoint, headers=headers, json={"path": path})
                response.raise_for_status()
            except (httpx.HTTPError, TypeError, KeyError, ValueError) as exc:
                if isinstance(exc, BootstrapError):
                    raise
                raise BootstrapError("An installed app could not use its media folder. Check Docker folder access and container user permissions, then resume. Existing files are preserved.") from None


def quality_profiles(payload, saved):
    """Verify reviewed native profiles without rewriting any app's profile rules."""
    from .config import CATALOG
    from .quality import select_profile

    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
        for key in ("sonarr", "radarr"):
            profile = payload.get("config", {}).get("integrations", {}).get(key, {}).get("quality_profile", "")
            if key not in payload["apps"] or not profile:
                continue
            port = payload["compose"]["services"][key]["ports"][0]["published"]
            try:
                response = client.get(f"http://127.0.0.1:{port}/api/v3/qualityprofile",
                                      headers={"X-Api-Key": saved[key]["api_key"]})
                response.raise_for_status()
                select_profile(response.json(), profile)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                raise BootstrapError(f"{CATALOG[key]['name']}: the reviewed {profile} quality profile could not be verified. Restore that profile in the app, then resume. No other quality was selected.") from None


def download_categories(payload, saved):
    """Create only the reviewed categories in this newly owned download client."""
    if "qbittorrent" not in payload["apps"]:
        return
    wanted = [key for key in ("sonarr", "radarr") if key in payload["apps"]]
    if not wanted:
        return
    require_write("qbittorrent", "category.create")
    port = payload["compose"]["services"]["qbittorrent"]["ports"][0]["published"]
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False, headers={"Referer": base}) as client:
            if not accepted(client.post(base + "/api/v2/auth/login", data=saved["qbittorrent"])):
                raise BootstrapError("The generated qBittorrent login was rejected.")
            for key in wanted:
                path = "/data/downloads/" + key
                response = client.get(base + "/api/v2/torrents/categories")
                response.raise_for_status()
                existing = response.json()
                if key in existing:
                    if existing[key].get("savePath") != path:
                        raise BootstrapError("A download category changed. Its existing settings are preserved; review it before resuming.")
                    continue
                response = client.post(base + "/api/v2/torrents/createCategory", data={"category": key, "savePath": path})
                response.raise_for_status()
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, BootstrapError):
            raise
        raise BootstrapError("Download categories could not be prepared. Resume after checking the newly installed qBittorrent app.") from None
