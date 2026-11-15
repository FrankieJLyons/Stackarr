"""Reviewed, durable post-import library scans, independent of an open browser.

Native Arr partial notifications remain intact. A new successful import triggers
one root scan of the reviewed matching sections, coalesced across a batch. History
is checkpointed only after Plex accepts the scan; failures retry after restart.
"""
import asyncio
import hashlib
import json
import re
import time

import httpx

from .adapters import require_write
from .integrations import IntegrationError, bounded_response
from .plex_wiring import plex_state
from .store import Conflict

KIND = 'Plex import discovery'


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class ImportRefresh:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport
        self.lock = asyncio.Lock()

    @staticmethod
    def initialized(db):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_refresh'").fetchone())

    def binding(self, app):
        config = self.store.config()[1]
        keys = ('plex', app)
        if not all(config.integrations[key].enabled for key in keys):
            raise ValueError('Import refresh apps are disabled')
        return {key: {'url': config.integrations[key].url,
                      'credential': signature(self.store.secret(key).get('api_key', ''))}
                for key in keys}

    async def read(self, client, app, path, params=None):
        config = self.store.config()[1]
        key = self.store.secret(app).get('api_key')
        if not key:
            raise ValueError('Missing app credential')
        response, data = await bounded_response(client, 'GET', config.integrations[app].url + path,
            headers={'Accept': 'application/json', 'X-Plex-Token' if app == 'plex' else 'X-Api-Key': key},
            params=params)
        response.raise_for_status()
        return json.loads(data) if data else {}

    async def latest(self, client, app):
        history = await self.read(client, app, '/api/v3/history',
            {'page': 1, 'pageSize': 1, 'sortKey': 'id', 'sortDirection': 'descending', 'eventType': 3})
        rows = history['records']
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError('Unexpected import history')
        if not rows:
            return 0
        row = rows[0]
        if row.get('eventType') != 'downloadFolderImported' or type(row.get('id')) is not int or row['id'] < 1:
            raise ValueError('Unexpected import event')
        return row['id']

    async def scope(self, client, app):
        binding = self.binding(app)
        config = self.store.config()[1]
        machine, libraries = await plex_state(client, config.integrations['plex'].url,
                                               self.store.secret('plex')['api_key'])
        roots = await self.read(client, app, '/api/v3/rootfolder')
        roots = sorted(row['path'] for row in roots)
        kind = 'movie' if app == 'radarr' else 'show'
        selected = sorted([list(row) for row in libraries if row[1] == kind and row[2] in roots])
        # A section containing another unrelated location must never be scanned
        # by this fallback, even if one of its locations matches an Arr root.
        ids = {row[0] for row in selected}
        if (not roots or not selected or {r[2] for r in selected} != set(roots)
                or any(not re.fullmatch(r'[0-9]{1,18}', key) for key in ids)
                or any(row[0] in ids and list(row) not in selected for row in libraries)):
            raise ValueError('Import roots need exclusive matching Plex sections')
        if binding != self.binding(app):
            raise Conflict('Connections changed during import refresh review')
        return {'binding': binding, 'machine': machine, 'libraries': selected, 'roots': roots}

    async def review(self, client):
        changes, notices = [], []
        config = self.store.config()[1]
        if not config.integrations['plex'].enabled:
            return changes, notices
        for app in ('sonarr', 'radarr'):
            if not config.integrations[app].enabled:
                continue
            if config.integrations[app].read_only:
                notices.append(app + ': imported native app is read-only; automatic scans were not enabled.')
                continue
            try:
                scope = await self.scope(client, app)
                cursor = await self.latest(client, app)
                with self.store.db() as db:
                    row = db.execute('SELECT scope FROM import_refresh WHERE app=?', (app,)).fetchone() if self.initialized(db) else None
                if row and json.loads(row[0]) == scope:
                    continue
                changes.append({'target': app, 'source': 'plex', 'kind': KIND,
                    'check': {'source': 'plex', 'target': app, 'state': 'proposed'},
                    'implementation': 'StackarrImportDiscovery', 'name': 'Automatic imported-title discovery',
                    'action': 'enable automatic scans after new imports', 'scope': scope, 'cursor': cursor,
                    'detail': 'After successful imports, Stackarr scans only the matching Plex movie or TV libraries. Imports in a batch are combined; failed scans retry. Existing Plex notifications and custom Seerr schedules are kept. Stackarr must remain running.'})
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IntegrationError):
                notices.append(app + ': automatic import discovery needs accessible import history and exclusive matching Plex library folders. Review connections again after setup.')
        return changes, notices

    async def apply(self, client, change):
        app, scope = change['target'], change['scope']
        from .native_import import require_writable

        require_writable(self.store, app, 'plex')
        require_write('plex', 'library.scan')
        if app not in ('radarr', 'sonarr') or await self.scope(client, app) != scope:
            raise Conflict('Import folders or Plex server changed. Review discovery again.')
        with self.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS import_refresh (
                app TEXT PRIMARY KEY, scope TEXT NOT NULL, cursor INTEGER NOT NULL,
                scanned REAL NOT NULL DEFAULT 0)''')
            current = db.execute('SELECT scope FROM import_refresh WHERE app=?', (app,)).fetchone()
            if current and json.loads(current[0]) == scope:
                return {'target': app, 'state': 'preserved existing'}
            # Keep the review's history checkpoint: an import arriving between
            # review and apply must still cause a scan, including after restart.
            db.execute('INSERT OR REPLACE INTO import_refresh VALUES(?,?,?,0)',
                       (app, json.dumps(scope), change['cursor']))
        self.store.audit('import-discovery.enabled', app)
        return {'target': app, 'state': 'created'}

    async def tick(self):
        async with self.lock:
            with self.store.db() as db:
                if not self.initialized(db):
                    return
                rows = db.execute('SELECT app,scope,cursor,scanned FROM import_refresh').fetchall()
            async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False,
                                         transport=self.transport) as client:
                for app, raw, cursor, scanned in rows:
                    try:
                        scope = json.loads(raw)
                        if self.binding(app) != scope['binding']:
                            continue
                        if self.store.config()[1].integrations[app].read_only:
                            continue
                        newest = await self.latest(client, app)
                        if newest <= cursor or time.time() - scanned < 60:
                            continue
                        if await self.scope(client, app) != scope:
                            continue
                        require_write('plex', 'library.scan')
                        for section in sorted({row[0] for row in scope['libraries']}):
                            # No path parameter: Plex's partial endpoint can
                            # acknowledge a new directory without discovering it.
                            if self.binding(app) != scope['binding']:
                                raise Conflict('Connections changed before scan')
                            await self.read(client, 'plex', '/library/sections/' + section + '/refresh')
                            self.store.audit('import-discovery.scan-started', app)
                        with self.store.db() as db:
                            db.execute('UPDATE import_refresh SET cursor=?,scanned=? WHERE app=? AND scope=? AND cursor=?',
                                       (newest, time.time(), app, raw, cursor))
                    except Exception:
                        # Do not log upstream URLs, tokens or private file paths.
                        self.store.audit('import-discovery.retry-pending', app)

    async def work(self):
        while True:
            try:
                await self.tick()
            except Exception:
                # A transient local database/storage error must not permanently
                # terminate discovery. Durable cursors remain unadvanced.
                pass
            await asyncio.sleep(15)
