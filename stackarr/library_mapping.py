"""Preview the route from qBittorrent staging through Arr imports into Plex libraries."""

import copy
import json
import secrets
import time
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from .adapters import require_write
from .config import Model
from .download_protection import address, binding, qbit_client, request
from .native_import import require_writable
from .store import Conflict

APPS = ('sonarr', 'radarr')
NOTICE = ('Downloads stay in a staging folder. Sonarr or Radarr imports completed media into the selected Plex library. '
          'Existing titles and downloads are not moved, searched or deleted. This sets the default for new requests through '
          'Stackarr; other request tools keep their own folder choices. Plex must finish its scan before playback appears.')


class MappingIntent(Model):
    app: Literal['sonarr', 'radarr']
    library: str = Field(default='', max_length=1100)


def host(value):
    return PureWindowsPath(value) if PureWindowsPath(value).drive else PurePosixPath(value)


def translated(record, directory, *, writable=True):
    path = host(directory)
    choices = []
    for mount in record['mounts']:
        root = host(mount['source'])
        if path.is_relative_to(root) and (not writable or mount['writable']):
            choices.append((len(root.parts), str(PurePosixPath(mount['target']).joinpath(*path.relative_to(root).parts))))
    if not choices:
        raise ValueError('The media apps do not share this Plex folder. Review their storage mounts; Stackarr will not change mounts or move files automatically.')
    longest = max(size for size, _ in choices)
    paths = {path for size, path in choices if size == longest}
    if len(paths) != 1:
        raise ValueError('More than one container path reaches this folder. Review the storage mounts first.')
    result = paths.pop()
    # A nested container mount can shadow the apparent shared folder.
    covering = [mount for mount in record['mounts'] if PurePosixPath(result).is_relative_to(PurePosixPath(mount['target']))]
    actual = max(covering, key=lambda mount: len(PurePosixPath(mount['target']).parts))
    resolved = host(actual['source']).joinpath(*PurePosixPath(result).relative_to(PurePosixPath(actual['target'])).parts)
    if resolved != path or (writable and not actual['writable']):
        raise ValueError('A nested mount hides this shared folder. Review container storage before mapping.')
    return result


def owned(config, topology, app):
    url = urlsplit(config.url)
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', 'host.docker.internal'} or url.path:
        raise ValueError('Automatic folder mapping requires a verified local installation connection.')
    records = [row for row in topology['apps'] if row['app'] == app and row['port'] == url.port]
    if len(records) != 1:
        raise ValueError('This app has no matching running installation receipt. Check the saved connection and installation.')
    return records[0]


def values(row):
    return {field['name']: field.get('value') for field in row.get('fields', [])}


class LibraryMapping:
    def __init__(self, store, probe, transport=None):
        self.store, self.probe, self.transport = store, probe, transport

    async def call(self, app, path, method='GET', payload=None):
        if method != 'GET':
            require_writable(self.store, app)
        key = self.store.secret(app).get('api_key')
        if not key:
            raise ValueError('Connect ' + app + ' in Apps first.')
        headers = {'Accept': 'application/json', 'X-Plex-Token' if app == 'plex' else 'X-Api-Key': key}
        if self.store.config()[1].integrations[app].request_host:
            headers['Host'] = self.store.config()[1].integrations[app].request_host
        async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=8, headers=headers) as client:
            raw = await request(client, method, address(self.store, app) + path, **({'json': payload} if payload is not None else {}))
        try:
            return json.loads(raw) if raw.strip() else None
        except (ValueError, UnicodeError):
            raise ValueError('An app returned unsupported library settings.') from None

    async def libraries(self):
        try:
            identity = (await self.call('plex', '/identity'))['MediaContainer']
            if identity.get('claimed') not in (True, 1) or not isinstance(identity.get('machineIdentifier'), str):
                raise ValueError('Finish claiming Plex before mapping library folders.')
            data = (await self.call('plex', '/library/sections'))['MediaContainer']
            sections = data.get('Directory', [] if data.get('size') == 0 else None)
            if not isinstance(sections, list) or len(sections) > 100:
                raise ValueError('Plex returned an unsupported library list.')
            rows = []
            for section in sections:
                if section['type'] not in {'movie', 'show'}:
                    continue
                for location in section.get('Location', []):
                    path = location['path']
                    if not isinstance(path, str) or len(path) > 1024 or any(ord(c) < 32 for c in path):
                        raise ValueError('Plex returned an unsupported folder.')
                    rows.append({'choice': str(section['key']) + ':' + path, 'id': str(section['key']), 'type': section['type'],
                                 'name': str(section.get('title', section['type']))[:200], 'path': path})
            if len(rows) > 100 or len({row['choice'] for row in rows}) != len(rows):
                raise ValueError('Plex returned ambiguous library folders.')
            return {'machine': identity['machineIdentifier'], 'libraries': sorted(rows, key=lambda row: row['choice'])}
        except (KeyError, TypeError):
            raise ValueError('Plex library access could not be verified. Finish connecting Plex first.') from None

    async def review(self, intent):
        app = intent.app
        revision, config = self.store.config()
        require_writable(self.store, app, 'qbittorrent')
        bound = {key: binding(self.store, key) for key in ('plex', app, 'qbittorrent')}
        libraries = await self.libraries()
        choices = [row for row in libraries['libraries'] if row['type'] == ('show' if app == 'sonarr' else 'movie')]
        chosen = [row for row in choices if row['choice'] == intent.library] if intent.library else choices
        if not intent.library and len(chosen) != 1:
            return {'app': app, 'choices': choices, 'needs_choice': True, 'notice': 'Choose the library and folder for new requests.'}
        if len(chosen) != 1:
            raise ValueError('That Plex library changed. Detect libraries again.')
        library = chosen[0]
        query = {'plex_port': urlsplit(config.integrations['plex'].url).port or 32400, 'folders': [library['path']]}
        topology = await self.probe(query)
        owned(config.integrations['plex'], topology, 'plex')
        arr = owned(config.integrations[app], topology, app)
        qbit = owned(config.integrations['qbittorrent'], topology, 'qbittorrent')
        root = translated(arr, topology['folders'][library['path']])
        staging = qbit['downloads'].get(app)
        if not staging or translated(qbit, staging['host']) != staging['path']:
            raise ValueError('A writable dedicated download staging folder could not be verified.')
        arr_staging = translated(arr, staging['host'])
        if arr_staging != staging['path']:
            raise ValueError('The downloader and media app use different paths for staging. Align their mounts before mapping; no remote path mapping was guessed.')
        library_host, staging_host = host(topology['folders'][library['path']]), host(staging['host'])
        if library_host.is_relative_to(staging_host) or staging_host.is_relative_to(library_host):
            raise ValueError('Downloads and the Plex library must be separate folders.')
        roots = await self.call(app, '/api/v3/rootfolder')
        clients = await self.call(app, '/api/v3/downloadclient')
        handling = await self.call(app, '/api/v3/config/downloadclient')
        if not isinstance(roots, list) or not isinstance(clients, list) or type(handling.get('enableCompletedDownloadHandling')) is not bool:
            raise ValueError('This app returned unsupported import settings.')
        if not handling['enableCompletedDownloadHandling']:
            await self.empty_queue(app)
        peer = urlsplit(config.integrations['qbittorrent'].peer_url or config.integrations['qbittorrent'].url)
        matched = [row for row in clients if row.get('implementation') == 'QBittorrent' and row.get('enable') is True
                   and values(row).get('host') == peer.hostname and values(row).get('port') == (peer.port or 80)
                   and bool(values(row).get('useSsl')) == (peer.scheme == 'https')
                   and (values(row).get('urlBase') or '').rstrip('/') == peer.path.rstrip('/')]
        if len(matched) != 1:
            raise ValueError('Review app connections first: exactly one enabled qBittorrent connection must match this downloader.')
        downloader = matched[0]
        category = values(downloader).get('tvCategory' if app == 'sonarr' else 'movieCategory', values(downloader).get('category'))
        if category != app:
            raise ValueError('The download client uses a custom category. Review it in the app before automatic mapping.')
        await self.call(app, '/api/v3/downloadclient/test', 'POST', downloader)
        async with qbit_client(self.store, self.transport) as client:
            categories = await client.get('torrents/categories')
            preferences = await client.get('app/preferences')
        if not isinstance(categories, dict) or not isinstance(categories.get(app), dict):
            raise ValueError('The dedicated download category is missing. Finish connecting the installed apps first.')
        if categories[app].get('savePath', '').rstrip('/') != staging['path']:
            raise ValueError('The existing download category points elsewhere. Its downloads are preserved; review its save folder in qBittorrent first.')
        # This switch affects suggested paths for new torrents, never an existing torrent's storage.
        # Do not toggle automatic management or edit categories: those can relocate active downloads.
        if any(type(preferences.get(key)) is not bool for key in ('auto_tmm_enabled', 'use_category_paths_in_manual_mode')):
            raise ValueError('Update qBittorrent to a version with supported category path settings before mapping.')
        root_rows = [{'id': row['id'], 'path': row['path']} for row in roots]
        if any(row['path'] == root and row.get('accessible') is False for row in roots):
            raise ValueError('The media app cannot access this Plex folder. Check folder permissions first.')
        return {'app': app, 'revision': revision, 'bindings': bound, 'library': library, 'libraries': libraries,
                'query': query, 'topology': topology, 'root': root, 'staging': staging['path'], 'roots': root_rows,
                'downloader': downloader, 'handling': handling, 'category': categories[app],
                'preferences': {key: preferences.get(key) for key in ('auto_tmm_enabled', 'use_category_paths_in_manual_mode')},
                'notification': await self.notification(app, root, library['path']),
                'enable_category_paths': not preferences['auto_tmm_enabled'] and not preferences['use_category_paths_in_manual_mode'],
                'create_root': not any(row['path'] == root for row in roots), 'needs_choice': False}

    async def empty_queue(self, app):
        queue = await self.call(app, '/api/v3/queue?page=1&pageSize=1')
        if not isinstance(queue, dict) or queue.get('totalRecords') != 0 or queue.get('records') != []:
            raise ValueError('Completed imports are disabled and this app has queued downloads. Review those in the app before enabling automatic imports.')

    async def notification(self, app, root, plex_path):
        if self.store.config()[1].integrations['plex'].read_only:
            return {'state': 'read-only', 'detail': 'Plex stays read-only. Its existing scan settings are preserved; open Plex to scan if automatic detection is not already enabled.'}
        current = await self.call(app, '/api/v3/notification')
        if not isinstance(current, list):
            raise ValueError('Existing Plex notifications could not be checked.')
        if any(row.get('implementation') == 'PlexServer' for row in current):
            return {'state': 'preserved', 'detail': 'Existing Plex notifications are preserved. Check that they scan the selected library.', 'before': current}
        schemas = await self.call(app, '/api/v3/notification/schema')
        schema = next((row for row in schemas if row.get('implementation') == 'PlexServer'), None)
        if not schema or not schema.get('supportsOnDownload') or not schema.get('supportsOnUpgrade'):
            raise ValueError('This app cannot prepare a supported Plex import notification.')
        payload = copy.deepcopy({key: schema[key] for key in ('implementation', 'configContract', 'fields')})
        if not {'host', 'port', 'useSsl', 'authToken', 'updateLibrary', 'mapFrom', 'mapTo'} <= values(payload).keys():
            raise ValueError('This app cannot translate its import path for Plex notifications.')
        plex = self.store.config()[1].integrations['plex']
        peer = urlsplit(plex.peer_url or plex.url)
        fields = {'host': peer.hostname, 'port': peer.port or (443 if peer.scheme == 'https' else 80),
                  'useSsl': peer.scheme == 'https', 'urlBase': peer.path.rstrip('/'),
                  'authToken': self.store.secret('plex')['api_key'], 'updateLibrary': True,
                  'mapFrom': root if root != plex_path else '', 'mapTo': plex_path if root != plex_path else ''}
        for field in payload['fields']:
            if field['name'] in fields:
                field['value'] = fields[field['name']]
        payload.update(name='Stackarr Plex after imports', tags=[], onDownload=True, onUpgrade=True, onRename=False, onGrab=False)
        if app == 'sonarr' and schema.get('supportsOnImportComplete'):
            payload['onImportComplete'] = True
        return {'state': 'create', 'detail': 'Notify Plex after a successful import or upgrade.', 'before': current, 'payload': payload}

    @staticmethod
    def public(plan):
        if plan.get('needs_choice'):
            return plan
        return {'app': plan['app'], 'needs_choice': False, 'library': plan['library'], 'root': plan['root'], 'staging': plan['staging'],
                'create_root': plan['create_root'], 'enable_imports': not plan['handling']['enableCompletedDownloadHandling'],
                'enable_category_paths': plan['enable_category_paths'],
                'refresh': plan['notification']['detail'], 'notice': NOTICE}

    def check(self, plan):
        require_writable(self.store, plan['app'], 'qbittorrent')
        if self.store.config()[0] != plan['revision'] or any(binding(self.store, key) != value for key, value in plan['bindings'].items()):
            raise Conflict('App connections changed. Preview the library mapping again.')

    def save(self, identity, run):
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS library_mapping_runs (id TEXT PRIMARY KEY, app TEXT, created REAL, value BLOB)')
            db.execute('INSERT INTO library_mapping_runs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (identity, run['app'], time.time(), self.store.cipher.encrypt(json.dumps(run).encode())))

    def saved(self, app):
        with self.store.db() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='library_mapping_runs'").fetchone()
            rows = db.execute('SELECT id,value FROM library_mapping_runs WHERE app=? ORDER BY created DESC LIMIT 20', (app,)).fetchall() if exists else []
        return [(row[0], json.loads(self.store.cipher.decrypt(row[1]))) for row in rows]

    def status(self):
        return {app: [{'id': identity, 'state': run['state'], 'library': run['library']['name'], 'root': run['root']}
                      for identity, run in self.saved(app)] for app in APPS}

    async def apply(self, plan):
        self.check(plan)
        current = await self.review(MappingIntent(app=plan['app'], library=plan['library']['choice']))
        if current != plan:
            raise Conflict('Libraries, mounts or download settings changed. Preview the mapping again.')
        app, identity = plan['app'], secrets.token_hex(16)
        run = copy.deepcopy(plan) | {'state': 'applying', 'root_created': None}
        self.save(identity, run)
        try:
            if plan['enable_category_paths']:
                require_write('qbittorrent', 'category-paths.configure')
                async with qbit_client(self.store, self.transport) as client:
                    preferences = await client.get('app/preferences')
                    if {key: preferences.get(key) for key in plan['preferences']} != plan['preferences']:
                        raise Conflict('qBittorrent path settings changed.')
                    self.check(plan)
                    await client.post('app/setPreferences', {'json': json.dumps({'use_category_paths_in_manual_mode': True})})
                    if (await client.get('app/preferences')).get('use_category_paths_in_manual_mode') is not True:
                        raise ValueError('qBittorrent category paths did not verify.')
            if plan['create_root']:
                require_write(app, 'root-folder.create')
                self.check(plan)
                created = await self.call(app, '/api/v3/rootfolder', 'POST', {'path': plan['root']})
                if not isinstance(created, dict) or created.get('path') != plan['root'] or created.get('accessible') is False:
                    raise ValueError('The new root folder did not verify.')
                run['root_created'] = created.get('id')
                self.save(identity, run)
            if not plan['handling']['enableCompletedDownloadHandling']:
                require_write(app, 'completed-imports.configure')
                if await self.call(app, '/api/v3/config/downloadclient') != plan['handling']:
                    raise Conflict('Completed download settings changed.')
                await self.empty_queue(app)
                self.check(plan)
                await self.call(app, '/api/v3/config/downloadclient/' + str(plan['handling']['id']), 'PUT',
                                plan['handling'] | {'enableCompletedDownloadHandling': True})
            handling = await self.call(app, '/api/v3/config/downloadclient')
            roots = await self.call(app, '/api/v3/rootfolder')
            if not handling.get('enableCompletedDownloadHandling') or not any(row['path'] == plan['root'] and row.get('accessible') is not False for row in roots):
                raise ValueError('The import folder and handling settings did not verify.')
            if await self.libraries() != plan['libraries'] or await self.probe(plan['query']) != plan['topology']:
                raise Conflict('Plex libraries or storage changed during setup.')
            note = plan['notification']
            if note['state'] == 'create':
                require_write(app, 'plex-notification.create')
                require_writable(self.store, 'plex')
                if await self.call(app, '/api/v3/notification') != note['before']:
                    raise Conflict('Plex notifications changed.')
                await self.call(app, '/api/v3/notification/test', 'POST', note['payload'])
                self.check(plan)
                if await self.call(app, '/api/v3/notification') != note['before']:
                    raise Conflict('Plex notifications changed during testing.')
                created = await self.call(app, '/api/v3/notification', 'POST', note['payload'])
                if not isinstance(created, dict) or type(created.get('id')) is not int:
                    raise ValueError('The notification did not verify.')
                verified = await self.call(app, '/api/v3/notification/' + str(created['id']))
                if (not isinstance(verified, dict) or any(verified.get(key) != value for key, value in note['payload'].items() if key != 'fields')
                        or any(values(verified).get(key) != value for key, value in values(note['payload']).items() if key != 'authToken')):
                    raise ValueError('The saved notification did not verify.')
                await self.call(app, '/api/v3/notification/test', 'POST', verified)
            self.check(plan)
            run['state'] = 'applied'
        except (ValueError, Conflict):
            run['state'] = 'needs-review'
        self.save(identity, run)
        self.store.audit('library-mapping.' + run['state'], app)
        return {'id': identity, 'state': run['state'], 'message': ('Library mapping saved and verified. ' + NOTICE) if run['state'] == 'applied'
                else 'Some setup may have completed. Inspect the app and preview again. The previous settings are retained in the recovery record.'}

    async def request_root(self, app, server):
        """Revalidate before a new request; never silently fall back to the wrong library."""
        history = self.saved(app)
        if not history:
            return None
        _, run = history[0]
        if run['state'] == 'paused':
            return None
        if run['state'] != 'applied' or any(binding(self.store, key) != value for key, value in run['bindings'].items()):
            raise ValueError('Review the saved Plex library mapping before requesting a new title.')
        libraries = await self.libraries()
        # Adding an unrelated Plex library does not change this explicit mapping.
        # Retain the server, selected folder and complete storage checks; never
        # automatically pick a different library when the saved one disappears.
        if (libraries['machine'] != run['libraries']['machine'] or run['library'] not in libraries['libraries']
                or await self.probe(run['query']) != run['topology']):
            raise ValueError('The Plex libraries or media mounts changed. Review library mapping before requesting.')
        roots = await self.call(app, '/api/v3/rootfolder')
        if not any(row['path'] == run['root'] and row.get('accessible') is not False for row in roots):
            raise ValueError('The mapped import folder is unavailable. Review library mapping before requesting.')
        clients = await self.call(app, '/api/v3/downloadclient')
        handling = await self.call(app, '/api/v3/config/downloadclient')
        if run['downloader'] not in clients or handling.get('enableCompletedDownloadHandling') is not True:
            raise ValueError('The download client or completed-import settings changed. Review library mapping before requesting.')
        async with qbit_client(self.store, self.transport) as client:
            categories = await client.get('torrents/categories')
            preferences = await client.get('app/preferences')
        if (categories.get(app) != run['category'] or not (preferences.get('auto_tmm_enabled') is True or
                                                         preferences.get('use_category_paths_in_manual_mode') is True)):
            raise ValueError('Download staging settings changed. Review library mapping before requesting.')
        settings = await self.call('seerr', '/api/v1/settings/' + app)
        actual = next((row for row in settings if row.get('id') == server['id']), None)
        integration = self.store.config()[1].integrations[app]
        peer = urlsplit(integration.peer_url or integration.url)
        if (not actual or actual.get('hostname') != peer.hostname or actual.get('port') != (peer.port or (443 if peer.scheme == 'https' else 80))
                or actual.get('useSsl', False) != (peer.scheme == 'https') or (actual.get('baseUrl') or '').rstrip('/') != peer.path.rstrip('/')
                or actual.get('apiKey') != run['bindings'][app]['credential'].get('api_key')):
            raise ValueError('Seerr points to a different app. Review its connection before using the library mapping.')
        return run['root']

    def pause(self, app):
        history = self.saved(app)
        if history:
            identity, run = history[0]
            run['state'] = 'paused'
            self.save(identity, run)
        return {'message': 'Stackarr’s folder override is paused. Existing roots, downloads and completed-import settings remain in the apps.'}
