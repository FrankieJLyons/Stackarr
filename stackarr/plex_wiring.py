"""Reviewed native import notifications and Seerr's own availability schedule.

No controller polling, file watching, library creation or availability overrides.
"""

import copy
from urllib.parse import urlsplit

import httpx

from .adapters import require_write
from .config import CATALOG
from .store import Conflict

JOB = 'plex-recently-added-scan'
DEFAULT_SCHEDULES = {'*/5 * * * *', '0 */5 * * * *'}
SCHEDULE = '* * * * *'


async def plex_state(client, base, token):
    headers = {'X-Plex-Token': token, 'Accept': 'application/json'}
    response = await client.get(base + '/identity', headers=headers)
    response.raise_for_status()
    identity = response.json()['MediaContainer']
    if identity.get('claimed') not in {True, 1}:
        raise ValueError('Plex server must be claimed before sharing its connection')
    machine = identity['machineIdentifier']
    if not isinstance(machine, str) or not machine:
        raise ValueError('Missing server identity')
    response = await client.get(base + '/library/sections', headers=headers)
    response.raise_for_status()
    container = response.json()['MediaContainer']
    sections = container.get('Directory', [] if container.get('size') == 0 else None)
    if not isinstance(sections, list):
        raise ValueError('Invalid library response')
    libraries = [(str(section['key']), section['type'], location['path'])
                 for section in sections if section['type'] in {'movie', 'show'}
                 for location in section.get('Location', [])]
    return machine, sorted(libraries)


def fields(payload):
    return {field['name']: field.get('value') for field in payload['fields']}


async def build(store, client, *, checks):
    revision, config = store.config()
    plex = config.integrations['plex']
    targets = [key for key in ('sonarr', 'radarr') if config.integrations[key].enabled]
    if not plex.enabled or not targets:
        return [], []
    selected = {key: {'source': 'plex', 'target': key, 'state': 'unavailable'} for key in targets}
    if config.integrations['seerr'].enabled:
        selected['seerr'] = {'source': 'plex', 'target': 'seerr', 'state': 'unavailable'}
    checks.extend(selected.values())
    token = store.secret('plex').get('api_key')
    if not token:
        return [], ['Finish connecting Plex before reviewing automatic library refresh.']
    changes, notices = [], []
    try:
        machine, libraries = await plex_state(client, plex.url, token)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return [], ['Plex library access could not be verified. Confirm this server is claimed to the expected Plex account, then finish connecting it and review again. No refresh settings changed.']
    if not libraries:
        return [], ['Plex has no movie or TV libraries yet. Add and connect libraries when ready; no libraries were created.']
    peer = urlsplit(plex.peer_url or plex.url)
    common = {'revision': revision, 'plex_base': plex.url, 'plex_key': token,
              'machine': machine, 'libraries': libraries}
    for target in targets:
        app, key = config.integrations[target], store.secret(target).get('api_key')
        if not key:
            continue
        headers = {'X-Api-Key': key}
        try:
            response = await client.get(app.url + '/api/v3/notification', headers=headers)
            response.raise_for_status()
            if any(row.get('implementation') == 'PlexServer' for row in response.json()):
                selected[target]['state'] = 'preserved'
                notices.append(f"{CATALOG[target]['name']}: existing Plex notifications are preserved; check their destination and import triggers in that app.")
                continue
            response = await client.get(app.url + '/api/v3/rootfolder', headers=headers)
            response.raise_for_status()
            kind = 'show' if target == 'sonarr' else 'movie'
            roots = sorted(row['path'] for row in response.json())
            if not any(path in roots for _, library_type, path in libraries if library_type == kind):
                raise ValueError('Plex and import library paths differ')
            response = await client.get(app.url + '/api/v3/notification/schema', headers=headers)
            response.raise_for_status()
            schema = next(row for row in response.json() if row.get('implementation') == 'PlexServer')
            if not schema.get('supportsOnDownload') or not schema.get('supportsOnUpgrade'):
                raise ValueError('Import notifications unsupported')
            payload = copy.deepcopy({name: schema[name] for name in ('implementation', 'configContract', 'fields')})
            available = fields(payload)
            if not {'host', 'port', 'useSsl', 'authToken', 'updateLibrary'} <= available.keys():
                raise ValueError('Unsupported Plex notification schema')
            values = {'host': peer.hostname, 'port': peer.port or (443 if peer.scheme == 'https' else 80),
                      'useSsl': peer.scheme == 'https', 'urlBase': peer.path.rstrip('/'),
                      'authToken': token, 'updateLibrary': True, 'mapFrom': '', 'mapTo': ''}
            for field in payload['fields']:
                if field['name'] in values:
                    field['value'] = values[field['name']]
            payload.update(name='Stackarr Plex after imports', tags=[], onDownload=True, onUpgrade=True,
                           onRename=False, onGrab=False)
            if target == 'sonarr' and schema.get('supportsOnImportComplete'):
                payload['onImportComplete'] = True
            selected[target]['state'] = 'proposed'
            changes.append({**common, 'source': 'plex', 'target': target, 'check': selected[target],
                            'base': app.url, 'key': key, 'path': '/api/v3/notification',
                            'implementation': 'PlexServer', 'name': payload['name'], 'kind': 'Plex import refresh',
                            'payload': payload, 'roots': roots,
                            'detail': 'Notify the connected Plex server after successful imports and upgrades. Existing Plex notifications are preserved; no deletion triggers or trash-emptying settings are enabled.'})
        except (httpx.HTTPError, ValueError, TypeError, KeyError, StopIteration):
            notices.append(f"{CATALOG[target]['name']}: could not verify matching Plex library paths and import notifications. Existing settings are preserved.")
    if 'seerr' in selected:
        app, key = config.integrations['seerr'], store.secret('seerr').get('api_key')
        if not key:
            return changes, notices
        try:
            headers = {'X-Api-Key': key}
            response = await client.get(app.url + '/api/v1/settings/plex', headers=headers)
            response.raise_for_status()
            settings = response.json()
            enabled = {str(row['id']) for row in settings['libraries'] if row.get('enabled') is True}
            if settings.get('machineId') != machine:
                raise ValueError('Connect the correct Plex server and libraries in Seerr')
            arr_roots = {}
            for target in targets:
                arr = config.integrations[target]
                response = await client.get(arr.url + '/api/v3/rootfolder',
                                            headers={'X-Api-Key': store.secret(target).get('api_key', '')})
                response.raise_for_status()
                roots = sorted(row['path'] for row in response.json())
                kind = 'movie' if target == 'radarr' else 'show'
                if not any(key in enabled and library_type == kind and path in roots
                           for key, library_type, path in libraries):
                    raise ValueError('Enable a library matching the import folder')
                arr_roots[target] = roots
            response = await client.get(app.url + '/api/v1/settings/jobs', headers=headers)
            response.raise_for_status()
            job = next(row for row in response.json() if row.get('id') == JOB)
            if job['cronSchedule'] not in DEFAULT_SCHEDULES:
                selected['seerr']['state'] = 'preserved'
                notices.append('Seerr: existing Plex availability schedule is preserved. Automatic availability depends on its enabled libraries and successful scans.')
            else:
                selected['seerr']['state'] = 'proposed'
                changes.append({**common, 'source': 'plex', 'target': 'seerr', 'check': selected['seerr'],
                                'base': app.url, 'key': key, 'path': f'/api/v1/settings/jobs/{JOB}/schedule',
                                'implementation': 'PlexRecentlyAdded', 'name': 'Plex availability checks',
                                'kind': 'Plex availability schedule', 'payload': {'schedule': SCHEDULE},
                                'previous_schedule': job['cronSchedule'], 'enabled_libraries': sorted(enabled),
                                'arr_roots': arr_roots,
                                'action': 'change the default schedule after verifying the connected Plex libraries',
                                'detail': 'Check recently added Plex media every minute using Seerr’s own background job. Plex must finish matching first; custom schedules are preserved. This does not mark an import as playable or start a full scan.'})
        except (httpx.HTTPError, ValueError, TypeError, KeyError, StopIteration):
            notices.append('Seerr: select this Plex server and enable its movie/TV libraries, then review availability checks again. No schedule changed.')
    return changes, notices


def current(store, change):
    if (store.config()[0] != change['revision']
            or store.secret('plex').get('api_key') != change['plex_key']
            or store.secret(change['target']).get('api_key') != change['key']):
        raise Conflict('Settings changed. Review automatic library refresh again.')


async def apply(store, client, change):
    target = change['target']
    schedule = change['kind'] == 'Plex availability schedule'
    require_write(target, 'plex-scan-schedule.configure' if schedule else 'plex-notification.create')
    current(store, change)
    if await plex_state(client, change['plex_base'], change['plex_key']) != (change['machine'], change['libraries']):
        raise Conflict('Plex server or libraries changed. Review again.')
    endpoint, headers = change['base'] + change['path'], {'X-Api-Key': change['key']}
    if schedule:
        config = store.config()[1]
        for app, expected in change['arr_roots'].items():
            response = await client.get(config.integrations[app].url + '/api/v3/rootfolder',
                                        headers={'X-Api-Key': store.secret(app).get('api_key', '')})
            response.raise_for_status()
            if sorted(row['path'] for row in response.json()) != expected:
                raise Conflict('Import library folders changed. Review again.')
        response = await client.get(change['base'] + '/api/v1/settings/plex', headers=headers)
        response.raise_for_status()
        settings = response.json()
        enabled = sorted(str(row['id']) for row in settings['libraries'] if row.get('enabled') is True)
        if settings.get('machineId') != change['machine'] or enabled != change['enabled_libraries']:
            raise Conflict('Seerr library selection changed. Review again.')
        response = await client.get(change['base'] + '/api/v1/settings/jobs', headers=headers)
        response.raise_for_status()
        job = next((row for row in response.json() if row.get('id') == JOB), None)
        if job is None:
            raise ValueError('Plex availability job unavailable')
        if job['cronSchedule'] != change['previous_schedule']:
            return {'target': target, 'state': 'preserved existing'}
        current(store, change)
        response = await client.post(endpoint, headers=headers, json=change['payload'])
        response.raise_for_status()
        response = await client.get(change['base'] + '/api/v1/settings/jobs', headers=headers)
        response.raise_for_status()
        if not any(row.get('id') == JOB and row.get('cronSchedule') == SCHEDULE for row in response.json()):
            raise ValueError('Availability schedule did not verify')
    else:
        response = await client.get(endpoint, headers=headers)
        response.raise_for_status()
        if any(row.get('implementation') == 'PlexServer' for row in response.json()):
            return {'target': target, 'state': 'preserved existing'}
        response = await client.get(change['base'] + '/api/v3/rootfolder', headers=headers)
        response.raise_for_status()
        if sorted(row['path'] for row in response.json()) != change['roots']:
            raise Conflict('Import library folders changed. Review again.')
        response = await client.post(endpoint + '/test', headers=headers, json=change['payload'])
        response.raise_for_status()
        current(store, change)
        response = await client.get(endpoint, headers=headers)
        response.raise_for_status()
        if any(row.get('implementation') == 'PlexServer' for row in response.json()):
            return {'target': target, 'state': 'preserved existing'}
        response = await client.post(endpoint, headers=headers, json=change['payload'])
        response.raise_for_status()
        response = await client.get(endpoint, headers=headers)
        response.raise_for_status()
        saved = next((row for row in response.json()
                      if row.get('implementation') == 'PlexServer' and row.get('name') == change['name']
                      and type(row.get('id')) is int and row['id'] > 0
                      and all(row.get(name) == value for name, value in change['payload'].items() if name != 'fields')
                      and all(fields(row).get(name) == value for name, value in fields(change['payload']).items()
                              if name in {'host', 'port', 'useSsl', 'updateLibrary', 'mapFrom', 'mapTo'})
                      and fields(row).get('authToken') in {change['plex_key'], '********'}), None)
        if saved is None:
            raise ValueError('Plex import notification did not verify')
        # The Arr APIs mask saved API-key fields. Testing the saved resource ID
        # makes the app resolve its own credential; supplying our candidate again
        # would only retest an unsaved token and could hide a bad save.
        response = await client.post(endpoint + '/test', headers=headers, json=saved)
        response.raise_for_status()
        current(store, change)
    store.audit('connection.created', target)
    return {'target': target, 'state': 'created'}
