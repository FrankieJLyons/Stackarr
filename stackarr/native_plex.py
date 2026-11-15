"""Read the signed-in Windows user's Plex identity and libraries, never claim or scan."""

import hashlib
import json
import os
import re

import httpx

from .integrations import bounded_response


def configuration():
    if os.name != 'nt':
        raise ValueError('Native Plex detection requires the Windows host controller.')
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Plex, Inc.\Plex Media Server', access=winreg.KEY_READ) as key:
            token = winreg.QueryValueEx(key, 'PlexOnlineToken')[0]
            machine = winreg.QueryValueEx(key, 'ProcessedMachineIdentifier')[0]
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}', token):
            raise ValueError
        if not isinstance(machine, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', machine):
            raise ValueError
    except (OSError, ValueError):
        raise ValueError('Native Plex has no readable signed-in account. Open Plex and finish its account setup first.') from None
    return {'key': token, 'machine': machine, 'address': 'http://127.0.0.1:32400'}


async def inspect(transport=None, source_reader=configuration):
    from .native_import import Snapshot

    source = source_reader()
    async with httpx.AsyncClient(transport=transport, timeout=3, trust_env=False, follow_redirects=False,
                                headers={'Accept': 'application/json', 'X-Plex-Token': source['key']}) as client:
        async def read(path):
            response, data = await bounded_response(client, 'GET', source['address'] + path)
            if response.status_code != 200:
                raise ValueError('Native Plex did not accept its saved account.')
            return json.loads(data)['MediaContainer']
        identity = await read('/identity')
        if identity.get('claimed') not in (True, 1) or identity.get('machineIdentifier') != source['machine']:
            raise ValueError('The responding Plex server does not match the native Windows account.')
        libraries = await read('/library/sections')
    sections = libraries.get('Directory', [] if libraries.get('size') == 0 else None)
    if not isinstance(sections, list) or len(sections) > 100:
        raise ValueError('Native Plex returned unsupported libraries.')
    roots = []
    for section in sections:
        if section['type'] not in {'movie', 'show'}:
            continue
        for location in section.get('Location', []):
            value = {'id': str(section['key']), 'type': section['type'], 'name': section.get('title', section['type']), 'path': location['path']}
            if any(not isinstance(item, str) or len(item) > 1024 or any(ord(c) < 32 for c in item) for item in value.values()):
                raise ValueError('Native Plex returned an unsupported library folder.')
            roots.append(value)
    snapshot = Snapshot(app='plex', version=str(identity.get('version', '')), browser_address=source['address'],
                        root_folders=sorted(roots, key=lambda row: (row['id'], row['path']))).model_dump()
    if source != source_reader() or source['key'] in json.dumps(snapshot):
        raise ValueError('Native Plex account changed during detection. Check again.')
    fingerprint = hashlib.sha256(json.dumps([source, snapshot], sort_keys=True).encode()).hexdigest()
    return {'snapshot': snapshot, 'credential': {'api_key': source['key']}, 'fingerprint': fingerprint,
            'source_directory': source['machine']}
