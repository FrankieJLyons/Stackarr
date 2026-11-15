"""Bounded unauthenticated localhost hints; never adopt or configure applications."""

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

import httpx

from .config import CATALOG

# Only published local TCP ports are used. Labels/images are hints, not proof of ownership.
PORT_MAPPING = re.compile(r"(?:^|, )(?P<host>127\.0\.0\.1|0\.0\.0\.0):(?P<port>\d+)->(?P<target>\d+)/tcp(?=,|$)")
IMAGES = {
    key: {value['image'].split(':')[0], 'linuxserver/' + key, 'ghcr.io/linuxserver/' + key}
    for key, value in CATALOG.items()
}
IMAGES['seerr'].update({'ghcr.io/seerr-team/seerr', 'ghcr.io/seerr-team/seerr-develop'})


def docker_candidates(apps, *, runner=None):
    """Read a verified local context and narrow ps fields; never inspect env or volumes."""
    from .docker_runtime import executable

    if os.environ.get('DOCKER_HOST') or Path('/.dockerenv').exists() or Path('/run/.containerenv').exists():
        return {}, 'Docker discovery unavailable; only default local addresses were checked.'
    docker = executable()
    if not docker:
        return {}, 'Docker is not installed; only default local addresses were checked.'
    runner = runner or subprocess.run

    def command(args):
        result = runner([docker, *args], capture_output=True, text=True, encoding='utf-8',
                        errors='replace', timeout=4,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or len(result.stdout) > 262144:
            raise ValueError('Docker inventory unavailable')
        return result.stdout.strip()

    try:
        context = command(['context', 'show'])
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', context):
            raise ValueError('Unsupported context')
        endpoint = command(['context', 'inspect', context, '--format', '{{.Endpoints.docker.Host}}'])
        if not endpoint.startswith(('unix:///', 'npipe:////./pipe/')):
            raise ValueError('Remote context')
        template = '{"image":{{json .Image}},"service":{{json (.Label "com.docker.compose.service")}},"ports":{{json .Ports}}}'
        output = command(['--context', context, 'ps', '--format', template])
        candidates = {key: [] for key in apps if key in CATALOG}
        for line in output.splitlines()[:128]:
            row = json.loads(line)
            if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ('image', 'service', 'ports')):
                continue
            image = row['image'].split('@')[0].split(':')[0]
            for key in candidates:
                if row['service'] != key and image not in IMAGES[key]:
                    continue
                for match in PORT_MAPPING.finditer(row['ports']):
                    port, target = int(match['port']), int(match['target'])
                    if not 1 <= port <= 65535 or (target != CATALOG[key]['port'] and (key != 'qbittorrent' or target == 6881)):
                        continue
                    address = f'http://127.0.0.1:{port}'
                    if address not in candidates[key] and len(candidates[key]) < 3:
                        candidates[key].append(address)
        return candidates, 'Running Docker apps were checked for published local ports. Container labels are connection hints only.'
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return {}, 'Docker inventory could not be checked. Default local addresses were still checked; custom ports may be missed.'

PATHS = {"plex": "/identity", "sonarr": "/api/v3/system/status", "radarr": "/api/v3/system/status",
         "prowlarr": "/api/v1/system/status", "qbittorrent": "/api/v2/app/version", "seerr": "/api/v1/status?checkUpdateAvailable=false"}


def evidence(app, content):
    if app == "qbittorrent":
        return bool(re.fullmatch(rb"v?\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]*)\s*", content))
    try:
        body = json.loads(content)
    except (ValueError, UnicodeError):
        return False
    if not isinstance(body, dict):
        return False
    if app in ("sonarr", "radarr", "prowlarr"):
        return isinstance(body.get("appName"), str) and body["appName"].lower() == app and isinstance(body.get("version"), str)
    if app == "plex":
        identity = body.get("MediaContainer", {})
        return isinstance(identity, dict) and bool(identity.get("machineIdentifier")) and isinstance(identity.get("version"), str)
    return app == "seerr" and isinstance(body.get("version"), str) and isinstance(body.get("commitTag"), str)


async def discover(apps, *, enabled=False, transport=None, include_docker=False, runner=None):
    if not enabled or Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return {"scope": "unavailable", "results": [], "message": "Open the local Stackarr launcher on the installation computer to find local apps."}
    apps = list(dict.fromkeys(key for key in apps if key in CATALOG))
    candidates, notice = await asyncio.to_thread(docker_candidates, apps, runner=runner) if include_docker else ({}, '')
    targets = [(key, address, 'docker-published-port') for key in apps for address in candidates.get(key, [])]
    targets += [(key, f"http://127.0.0.1:{CATALOG[key]['port']}", 'default-port') for key in apps
                if f"http://127.0.0.1:{CATALOG[key]['port']}" not in candidates.get(key, [])]
    semaphore = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=2, follow_redirects=False, trust_env=False, transport=transport) as client:
        async def one(app, address, source):
            row = {"app": app, "state": "manual-check", "address": address, "source": source,
                   "detail": "Use Settings to connect and test this application.", "adopted": False}
            if app not in PATHS:
                return row
            async with semaphore:
                try:
                    async with client.stream("GET", row["address"] + PATHS[app], headers={"Accept": "application/json"}) as response:
                        if response.status_code in (401, 403):
                            return row | {"state": "credentials-required", "detail": "A service requires credentials here. Its identity is not confirmed; review the address before connecting."}
                        if response.status_code != 200:
                            return row | {"state": "unverified", "detail": "A service responded but did not provide a recognized API response."}
                        content = b""
                        async for chunk in response.aiter_bytes():
                            content += chunk
                            if len(content) > 65536:
                                return row | {"state": "unverified", "detail": "Response was too large to identify safely."}
                    match = evidence(app, content)
                    return row | {"state": "compatible-api" if match else "unverified",
                                  "detail": "A compatible API responded. Confirm the app and its credentials in Settings; no ownership is assumed." if match else "The response does not match this app's expected API. Check the address manually."}
                except (httpx.HTTPError, ValueError, TypeError):
                    return row | {"state": "not-detected", "detail": "No usable response at the default local address. The app may use another port, HTTPS or another computer."}
        async def bounded(app, address, source):
            try:
                return await asyncio.wait_for(one(app, address, source), timeout=8)
            except TimeoutError:
                return {"app": app, "state": "not-detected", "address": address, "source": source,
                        "detail": "The check timed out. Review the address and try again.", "adopted": False}
        rows = await asyncio.gather(*(bounded(*target) for target in targets))
    return {"scope": "localhost-and-docker-ports" if include_docker else "localhost-default-ports", "results": rows,
            "message": "These are connection hints, not installation or ownership proof. No credentials were sent and no apps were changed. " + notice}
