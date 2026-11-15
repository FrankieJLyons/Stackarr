"""Version-bounded Cleanuparr recipes; every recipe starts in app-wide dry-run."""

import asyncio
import copy
import json
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, model_validator

from .adapters import CLEANUP_FLAGS, require_write
from .config import Model
from .download_protection import Protection, address, binding, qbit_client, selected
from .library_mapping import LibraryMapping, values
from .native_import import require_writable
from .store import Conflict

VERSION = '2026-11-15.1'
SUPPORTED = {'2.10.11', '2.10.11.0'}
ARRS = ('sonarr', 'radarr', 'lidarr', 'readarr', 'whisparr', 'sportarr', 'lazylibrarian')
CONFIGS = ('general', *CLEANUP_FLAGS)
PATHS = {key: '/api/configuration/' + key for key in CONFIGS}
PATHS.update(stall='/api/queue-rules/stall', slow='/api/queue-rules/slow', clients='/api/configuration/download_client')
PATHS.update({'arr_' + key: '/api/configuration/' + key for key in ARRS})
RECIPES = [
    {'id': 'observe', 'name': 'Observe first', 'description': 'Preview failed-import and errored-download checks in Cleanuparr logs. No live cleanup.', 'recommended': True},
    {'id': 'media', 'name': 'Media safeguards', 'description': 'Apply qBittorrent filename exclusions and disable external program hooks. Cleanuparr stays in dry-run with its jobs paused.'},
    {'id': 'recover', 'name': 'Recover stuck downloads', 'description': 'Preview repeated failures and stalled public torrents. Private torrents, slow-only downloads and automatic replacement searches are excluded.'},
    {'id': 'completed', 'name': 'Clean completed downloads', 'description': 'Preview cleanup of public torrents in a verified post-import category, after both your ratio and minimum seeding time are met.'},
]
NOTICE = ('Cleanuparr dry-run is app-wide. This preset pauses other automatic jobs; their rules, connections and exclusions are retained. '
          'A separate live review and confirmation is required for cleanup. Restoring settings cannot restore deleted downloads or files.')


class Intent(Model):
    preset: Literal['observe', 'media', 'recover', 'completed'] = 'observe'
    block_archives: bool = Field(default=True, strict=True)
    connectivity_url: str = Field(default='', max_length=1000)
    client_id: str = Field(default='', max_length=36)
    category: str = Field(default='', max_length=128)
    ratio: float = Field(default=2, ge=1, le=1000, allow_inf_nan=False)
    seed_hours: int = Field(default=72, ge=1, le=87600, strict=True)
    delete_source_files: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def url(self):
        if self.connectivity_url:
            url = urlsplit(self.connectivity_url)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError('Use an HTTPS connectivity-check URL without embedded credentials or a fragment.')
        return self


def endpoint(value):
    url = urlsplit(value)
    return (url.scheme, url.hostname, url.port or (443 if url.scheme == 'https' else 80), url.path.rstrip('/'))


def identity(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('The app returned an unsupported rule or client identity.') from None


def public_value(value):
    """Configuration diffs contain flags/numbers only; never hosts, credentials or command text."""
    if type(value) in (bool, int, float) or value is None:
        return value
    if isinstance(value, list):
        return f'{len(value)} entries'
    if value in ('Include', 'Exclude', 'Public', 'Private', 'Both', 'Delete', 'Stop'):
        return value
    return 'Configured' if value else 'Not configured'


def diff(before, after, prefix=''):
    rows = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        name = prefix + key
        if isinstance(old, dict) and isinstance(new, dict):
            rows.extend(diff(old, new, name + '.'))
        else:
            rows.append({'setting': name, 'before': public_value(old), 'after': public_value(new)})
    return rows


class CleanupPresets:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport
        self.http = LibraryMapping(store, None, transport)
        self.protection = Protection(store, transport)

    def bindings(self):
        return {key: binding(self.store, key) for key in ('cleanuparr', 'qbittorrent', 'sonarr', 'radarr')}

    def check(self, plan):
        require_writable(self.store, 'cleanuparr')
        require_write('cleanuparr', 'presets.configure')
        if self.bindings() != plan['bindings'] or self.store.config()[0] != plan['revision']:
            raise Conflict('Connections or settings changed. Preview the Cleanuparr preset again.')

    async def call(self, path, method='GET', payload=None):
        return await self.http.call('cleanuparr', path, method, payload)

    async def snapshot(self):
        status = await self.call('/api/status')
        version = status.get('application', {}).get('version') if isinstance(status, dict) else None
        if version not in SUPPORTED:
            raise ValueError('Cleanuparr presets support verified version 2.10.11. Other versions need adapter verification; existing settings were preserved.')
        data = dict(zip(PATHS, await asyncio.gather(*(self.call(path) for path in PATHS.values())), strict=True))
        if isinstance(data['clients'], dict):
            data['clients'] = data['clients'].get('clients')
        data['version'] = version
        for key in CONFIGS:
            if not isinstance(data[key], dict):
                raise ValueError('Cleanuparr returned an unsupported configuration schema.')
        if type(data['general'].get('dryRun')) is not bool:
            raise ValueError('Cleanuparr does not expose a verified dry-run control.')
        for job, flags in CLEANUP_FLAGS.items():
            if any(type(data[job].get(flag)) is not bool for flag in flags):
                raise ValueError('A Cleanuparr job flag could not be verified.')
        for key in ('stall', 'slow', 'clients'):
            if not isinstance(data[key], list) or len(data[key]) > 200:
                raise ValueError('Cleanuparr returned an unsupported rule/client list.')
            data[key].sort(key=lambda row: str(row.get('id', '')))
        if not isinstance(data['download_cleaner'].get('clients'), list):
            raise ValueError('Cleanuparr download-cleaner capabilities could not be checked.')
        for key in ARRS:
            if not isinstance(data['arr_' + key], dict) or not isinstance(data['arr_' + key].get('instances'), list):
                raise ValueError('Cleanuparr source connections could not be checked.')
        return data

    def sources(self, snap):
        """Recovery must not silently include an unrelated source or per-app strike override."""
        config = self.store.config()[1]
        count = 0
        for key in ARRS:
            source = snap['arr_' + key]
            enabled = [row for row in source['instances'] if row.get('enabled') is True]
            if not enabled:
                continue
            if key not in ('sonarr', 'radarr') or not config.integrations[key].enabled:
                raise ValueError('Recovery requires Cleanuparr sources to match the Sonarr/Radarr connections in Stackarr. Review extra sources in Cleanuparr.')
            peer = config.integrations[key]
            if len(enabled) != 1 or endpoint(enabled[0].get('url', '')) != endpoint(peer.peer_url or address(self.store, key)):
                raise ValueError('A Cleanuparr source points to another library app. Review its connections first.')
            if source.get('failedImportMaxStrikes') != -1:
                raise ValueError('A library app overrides the failed-import strike limit. Use the global limit in Cleanuparr before selecting this recipe.')
            count += 1
        if not count:
            raise ValueError('Connect Sonarr or Radarr in Cleanuparr before enabling queue observation or recovery.')

    async def imported_categories(self, snap):
        config, result, active_categories = self.store.config()[1], [], set()
        peer = config.integrations['qbittorrent']
        if not peer.enabled:
            return []
        qpeer = endpoint(peer.peer_url or address(self.store, 'qbittorrent'))
        matched = [row for row in snap['clients'] if row.get('enabled') is True and row.get('typeName') == 'qBittorrent'
                   and endpoint(row.get('host', '')) == qpeer and not row.get('urlBase')]
        if len(matched) != 1:
            return []
        client_id = identity(matched[0]['id'])
        async with qbit_client(self.store, self.transport) as qbit:
            categories = await qbit.get('torrents/categories')
        for app in ('sonarr', 'radarr'):
            if not config.integrations[app].enabled or not self.store.secret(app).get('api_key'):
                continue
            clients = await self.http.call(app, '/api/v3/downloadclient')
            handling = await self.http.call(app, '/api/v3/config/downloadclient')
            if handling.get('enableCompletedDownloadHandling') is not True:
                continue
            for row in clients:
                fields = values(row)
                if (row.get('implementation') != 'QBittorrent' or row.get('enable') is not True
                        or fields.get('host') != qpeer[1] or fields.get('port') != qpeer[2]
                        or bool(fields.get('useSsl')) != (qpeer[0] == 'https')
                        or (fields.get('urlBase') or '').rstrip('/') != qpeer[3]):
                    continue
                category = fields.get('tvImportedCategory' if app == 'sonarr' else 'movieImportedCategory')
                active = fields.get('tvCategory' if app == 'sonarr' else 'movieCategory')
                if isinstance(active, str):
                    active_categories.add(active.casefold())
                if isinstance(category, str) and category and category != active and category in categories:
                    result.append({'client_id': client_id, 'category': category, 'app': app})
        return [row for row in result if row['category'].casefold() not in active_categories]

    async def queue_clients(self, snap):
        """Queue Cleaner is source-wide; reject mixed/foreign download clients for live recovery."""
        self.sources(snap)
        config = self.store.config()[1]
        if not config.integrations['qbittorrent'].enabled:
            raise ValueError('Connect qBittorrent before using the recovery recipe.')
        peer = endpoint(config.integrations['qbittorrent'].peer_url or address(self.store, 'qbittorrent'))
        clients = [row for row in snap['clients'] if row.get('enabled') is True]
        if (len(clients) != 1 or clients[0].get('typeName') != 'qBittorrent'
                or endpoint(clients[0].get('host', '')) != peer or clients[0].get('urlBase')):
            raise ValueError('Recovery supports one matching qBittorrent client in Cleanuparr. Review additional or mismatched clients in Cleanuparr first.')
        result = {}
        for app in ('sonarr', 'radarr'):
            if not any(row.get('enabled') is True for row in snap['arr_' + app]['instances']):
                continue
            rows = await self.http.call(app, '/api/v3/downloadclient')
            enabled = [row for row in rows if row.get('enable') is True]
            if len(enabled) != 1:
                raise ValueError('Recovery requires each connected library app to use only the matching qBittorrent client. Mixed-client queues need manual Cleanuparr rules.')
            fields = values(enabled[0])
            if (enabled[0].get('implementation') != 'QBittorrent' or fields.get('host') != peer[1]
                    or fields.get('port') != peer[2] or bool(fields.get('useSsl')) != (peer[0] == 'https')
                    or (fields.get('urlBase') or '').rstrip('/') != peer[3]):
                raise ValueError('A library app uses another download client. Review its connection before using recovery.')
            result[app] = enabled
        return result

    def history(self):
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='cleanup_preset_runs'").fetchone()
            rows = db.execute('SELECT id,created,value FROM cleanup_preset_runs ORDER BY created DESC LIMIT 20').fetchall() if table else []
        return [{'id': row[0], 'created': row[1], **{key: value for key, value in json.loads(self.store.cipher.decrypt(row[2])).items()
                                                 if key in ('state', 'preset', 'kind')}} for row in rows]

    def save(self, run):
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS cleanup_preset_runs (id TEXT PRIMARY KEY, created REAL, value BLOB)')
            db.execute('INSERT INTO cleanup_preset_runs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (run['id'], time.time(), self.store.cipher.encrypt(json.dumps(run).encode())))

    def run(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Choose a saved Cleanuparr change.')
        with self.store.db() as db:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='cleanup_preset_runs'").fetchone()
            row = db.execute('SELECT value FROM cleanup_preset_runs WHERE id=?', (key,)).fetchone() if table else None
        if not row:
            raise ValueError('Choose a saved Cleanuparr change.')
        return json.loads(self.store.cipher.decrypt(row[0]))

    async def status(self):
        snap = await self.snapshot()
        reason = ''
        try:
            categories = await self.imported_categories(snap)
        except (ValueError, Conflict):
            categories, reason = [], 'Check qBittorrent and library app connections to verify post-import categories.'
        recovery_blocker = ''
        try:
            await self.queue_clients(snap)
        except (ValueError, Conflict) as exc:
            recovery_blocker = str(exc)
        return {'version': snap['version'], 'recipe_version': VERSION, 'dry_run': snap['general']['dryRun'],
                'presets': RECIPES, 'default': 'observe', 'notice': NOTICE, 'history': self.history(),
                'imported_categories': categories, 'recovery_blocker': recovery_blocker, 'completed_blocker': '' if categories else reason or
                'Set a separate post-import category in Sonarr or Radarr’s qBittorrent settings, create that category in qBittorrent, then check again. Active download categories are not eligible.'}

    async def review(self, intent):
        before = await self.snapshot()
        plan = {'kind': 'preset', 'preset': intent.preset, 'intent': intent.model_dump(),
                'revision': self.store.config()[0], 'bindings': self.bindings(), 'snapshot': before, 'ops': []}
        after = copy.deepcopy(before)
        after['general']['dryRun'] = True
        for job, flags in CLEANUP_FLAGS.items():
            after[job].update(dict.fromkeys(flags, False))
        queue = after['queue_cleaner']
        saved_queue = copy.deepcopy(queue)
        queue.update(processNoContentId=False, downloadingMetadataMaxStrikes=0, cronExpression='0 0/15 * * * ?', useAdvancedScheduling=False)
        for section in ('failedImport', 'errored'):
            required = ('maxStrikes', 'ignorePrivate', 'deletePrivate', 'changeCategory')
            if not isinstance(queue.get(section), dict) or any(key not in queue[section] for key in required):
                raise ValueError('This Cleanuparr queue schema is unsupported.')
            queue[section].update(maxStrikes=6, ignorePrivate=True, deletePrivate=False, changeCategory=False)
        queue['failedImport'].update(skipIfNotFoundInClient=True, forceImport=False)
        if queue['failedImport'].get('patternMode') == 'Include' and not queue['failedImport'].get('patterns'):
            queue['failedImport']['patternMode'] = 'Exclude'
        if intent.preset not in ('observe', 'recover'):
            after['queue_cleaner'] = saved_queue
        if intent.preset in ('observe', 'recover'):
            self.sources(before)
            queue['enabled'] = True
        if intent.preset == 'recover':
            plan['queue_clients'] = await self.queue_clients(before)
            if any(row.get('enabled') is not False for row in before['stall'] + before['slow']):
                raise ValueError('Disable existing stall/slow rules in Cleanuparr before using this recipe; their definitions will be retained.')
            urls = [intent.connectivity_url] if intent.connectivity_url else before['general'].get('connectivityCheckUrls', [])
            if not urls:
                raise ValueError('Provide an HTTPS internet-check URL before enabling recovery. Cleanuparr will contact it to avoid strikes during an outage.')
            after['general'].update(connectivityCheckEnabled=True, connectivityCheckUrls=urls)
            rule = {'name': 'Stackarr public stalled v1', 'enabled': True, 'maxStrikes': 12, 'privacyType': 'Public',
                    'minCompletionPercentage': 0, 'maxCompletionPercentage': 95, 'deletePrivateTorrentsFromClient': False,
                    'changeCategory': False, 'resetStrikesOnProgress': True, 'minimumProgress': None}
            if any(row.get('name') == rule['name'] for row in before['stall']):
                raise ValueError('Restore the previous Stackarr recovery preset before creating another stalled-download rule.')
            plan['ops'].append({'app': 'cleanuparr', 'key': 'stall', 'path': PATHS['stall'], 'method': 'POST', 'before': None, 'after': rule})
        if intent.preset == 'media':
            from .download_protection import ProtectionIntent
            require_writable(self.store, 'qbittorrent')
            protection = await self.protection.review(ProtectionIntent(block_archives=intent.block_archives))
            plan['ops'].append({'app': 'qbittorrent', 'key': 'qbit', 'path': 'preferences', 'method': 'PUT',
                                'before': protection['before'], 'after': protection['after']})
        if intent.preset == 'completed':
            eligible = await self.imported_categories(before)
            if not any(row['client_id'] == intent.client_id and row['category'] == intent.category for row in eligible):
                raise ValueError('Choose a verified post-import category. Configure it in Sonarr/Radarr and qBittorrent first, then check again.')
            for client in before['download_cleaner']['clients']:
                if client.get('seedingRules') or any(client.get(key) and client[key].get('enabled') is not False
                    for key in ('unlinkedConfig', 'deadTorrentConfig', 'orphanedFilesConfig')):
                    raise ValueError('This download cleaner already has rules or other cleanup jobs. Restore the previous recipe or review those settings in Cleanuparr first; they were preserved.')
            rule = {'name': 'Stackarr completed v1', 'categories': [intent.category], 'trackerPatterns': [], 'tagsAny': [], 'tagsAll': [],
                    'privacyType': 'Public', 'maxRatio': intent.ratio, 'minSeedTime': intent.seed_hours, 'maxSeedTime': -1,
                    'minSeeders': 0, 'maxInactiveDays': -1, 'deleteSourceFiles': intent.delete_source_files, 'action': 'Delete'}
            plan['ops'].append({'app': 'cleanuparr', 'key': 'seed', 'path': '/api/seeding-rules/' + identity(intent.client_id),
                                'method': 'POST', 'before': None, 'after': rule, 'client_id': intent.client_id})
            after['download_cleaner'].update(enabled=True, cronExpression='0 0 * * * ?', useAdvancedScheduling=False)
        # Dry-run is always the first write, and verified before any scheduled job is enabled.
        config_ops = [{'app': 'cleanuparr', 'key': key, 'path': PATHS[key], 'method': 'PUT',
                       'before': self.config_value(key, before[key]), 'after': self.config_value(key, after[key])}
                      for key in CONFIGS if before[key] != after[key]]
        plan['ops'] = config_ops[:1] + plan['ops'] + config_ops[1:] if config_ops and config_ops[0]['key'] == 'general' else plan['ops'] + config_ops
        return plan

    @staticmethod
    def public(plan):
        intent = plan.get('intent') or {}
        scope = ['Private torrents are excluded. Replacement searches, blacklist sync, orphaned-file and unlinked-download cleanup stay off.']
        if plan['preset'] == 'media':
            scope = ['Cleanuparr jobs stay paused. qBittorrent filename exclusions apply to all new torrents, including private torrents; no torrent cleanup is enabled.']
        if plan['preset'] == 'completed':
            scope += [f"Public torrents in post-import category: {intent.get('category', '')}.",
                      f"Both ratio {intent.get('ratio')} and {intent.get('seed_hours')} seeding hours are required. No maximum-time override.",
                      'Source download files will be permanently deleted.' if intent.get('delete_source_files') else 'Source download files will be kept; only the torrent entry is removed.']
        elif plan['preset'] in ('observe', 'recover'):
            scope += ['Failed imports and client errors: six checks, every 15 minutes. Private torrents and downloads without a content ID are skipped.']
            if plan['preset'] == 'recover':
                scope += ['Stalled public torrents up to 95% complete: twelve checks, reset on progress. Slow-only and metadata-timeout removal are off.']
        if plan['kind'] == 'restore':
            scope = ['Restore the changed settings in app-wide dry-run. Previous live mode is not restored. Files and downloads already removed cannot be recovered by this action.']
        return {'kind': plan['kind'], 'preset': plan['preset'], 'notice': NOTICE,
                'scope': scope,
                'dry_run': plan['kind'] != 'live', 'changes': [
                    {'app': op['app'], 'section': op['key'], 'action': 'Create rule' if op['method'] == 'POST' else 'Remove preset rule' if op['method'] == 'DELETE' else 'Update settings',
                     'settings': diff(op['before'] or {}, op['after'] or {})} for op in plan['ops']],
                'intent': plan.get('intent'), 'live_warning': 'Live cleanup can remove torrents and permanently delete source files where enabled. It may act on existing eligible downloads. Settings restore cannot recover those files.' if plan['kind'] == 'live' else '',
                'media_notice': 'qBittorrent filename safeguards take effect for new torrents immediately when applied; Cleanuparr dry-run does not control qBittorrent. This is not antivirus.' if plan['preset'] == 'media' else ''}

    async def read_op(self, op):
        if op['app'] == 'qbittorrent':
            async with qbit_client(self.store, self.transport) as client:
                return selected(await client.get('app/preferences'))
        if op['key'] in ('stall', 'seed'):
            rows = await self.call(PATHS['stall'] if op['key'] == 'stall' else '/api/seeding-rules/' + identity(op['client_id']))
            matches = [row for row in rows if row.get('name') == (op['after'] or op['before'])['name']]
            if len(matches) > 1:
                raise Conflict('More than one rule matches this preset. Review it in Cleanuparr.')
            return matches[0] if matches else None
        return self.config_value(op['key'], await self.call(op['path']))

    @staticmethod
    def config_value(key, value):
        return {k: v for k, v in value.items() if k != 'clients'} if key == 'download_cleaner' else value

    @staticmethod
    def rule_matches(actual, wanted):
        return isinstance(actual, dict) and all(actual.get(key) == value for key, value in wanted.items())

    async def write_op(self, op):
        if op['app'] == 'qbittorrent':
            require_writable(self.store, 'qbittorrent')
            require_write('qbittorrent', 'protection.configure')
            await self.protection.cleanup()
            async with qbit_client(self.store, self.transport) as client:
                await client.post('app/setPreferences', {'json': json.dumps(op['after'])})
        else:
            await self.call(op['path'], op['method'], op['after'] if op['method'] != 'DELETE' else None)

    async def apply(self, plan):
        self.check(plan)
        if await self.snapshot() != plan['snapshot']:
            raise Conflict('Cleanuparr settings or connections changed after the preview. Review again.')
        if plan['kind'] == 'preset' and await self.review(Intent.model_validate(plan['intent'])) != plan:
            raise Conflict('The preset prerequisites changed. Preview again.')
        if plan['kind'] == 'live' and await self.live_review(plan['parent']) != plan:
            raise Conflict('Live cleanup prerequisites changed. Review again.')
        run = {**copy.deepcopy(plan), 'id': secrets.token_hex(16), 'state': 'applying'}
        expected = copy.deepcopy(plan['snapshot'])
        self.save(run)
        try:
            for op in run['ops']:
                self.check(plan)
                current = await self.read_op(op)
                if current != op['before']:
                    raise Conflict('A setting changed during apply. Previously completed changes have a recovery record.')
                if op['key'] != 'general':
                    if (await self.call(PATHS['general'])).get('dryRun') is not True:
                        raise Conflict('Cleanuparr left dry-run during apply. Review its settings before continuing.')
                op['state'] = 'sending'
                self.save(run)
                await self.write_op(op)
                actual = await self.read_op(op)
                if op['method'] == 'POST':
                    if not self.rule_matches(actual, op['after']):
                        raise ValueError('A created preset rule could not be verified.')
                    identity(actual.get('id'))
                    op['created'] = actual
                elif actual != op['after']:
                    raise ValueError('A saved preset setting could not be verified.')
                if op['app'] == 'cleanuparr':
                    if op['key'] == 'stall':
                        expected['stall'] = [row for row in expected['stall'] if row['name'] != (op['after'] or op['before'])['name']]
                        if actual:
                            expected['stall'].append(actual)
                        expected['stall'].sort(key=lambda row: row['id'])
                    elif op['key'] == 'seed':
                        client = next(row for row in expected['download_cleaner']['clients'] if row['downloadClientId'] == op['client_id'])
                        client['seedingRules'] = [row for row in client['seedingRules'] if row['name'] != (op['after'] or op['before'])['name']]
                        if actual:
                            client['seedingRules'].append(actual)
                    elif op['key'] == 'download_cleaner':
                        expected[op['key']].update(actual)
                    else:
                        expected[op['key']] = actual
                op['state'] = 'done'
                self.save(run)
            self.check(plan)
            run['applied_snapshot'] = await self.snapshot()
            if run['applied_snapshot'] != expected:
                raise Conflict('Another Cleanuparr setting changed during apply. Check the saved recovery record.')
            if run['applied_snapshot']['general']['dryRun'] != (plan['kind'] != 'live'):
                raise ValueError('The Cleanuparr operating mode could not be verified.')
            run['state'] = 'applied'
        except (ValueError, Conflict):
            run['state'] = 'uncertain'
        self.save(run)
        self.store.audit('cleanup-preset.' + run['state'], 'cleanuparr')
        return {'id': run['id'], 'state': run['state'], 'preset': run['preset'], 'kind': run['kind'],
                'message': ('Live cleanup enabled and verified.' if plan['kind'] == 'live' else 'Settings saved and verified. Cleanuparr remains in dry-run.') if run['state'] == 'applied'
                else 'The change could not be fully verified. Check Cleanuparr and preview restoring this saved change; no automatic retries were started.'}

    async def live_review(self, key):
        run = self.run(key)
        self.check(run)
        if run['state'] != 'applied' or run['kind'] != 'preset' or run['preset'] not in ('recover', 'completed'):
            raise ValueError('Live cleanup requires an applied recovery or completed-download preset. Observe first stays in dry-run; qBittorrent safeguards already work independently.')
        before = await self.snapshot()
        if before != run['applied_snapshot'] or before['general']['dryRun'] is not True:
            raise Conflict('Settings changed since this preset was applied. Preview and apply it again before enabling live cleanup.')
        # Recheck imported categories and the app bindings immediately before granting live access.
        if run['preset'] == 'completed':
            intent = Intent.model_validate(run['intent'])
            if not any(row['client_id'] == intent.client_id and row['category'] == intent.category for row in await self.imported_categories(before)):
                raise Conflict('The verified post-import category changed. Live cleanup was not enabled.')
        else:
            if await self.queue_clients(before) != run.get('queue_clients'):
                raise Conflict('A library download-client connection changed. Preview the recovery preset again before enabling live cleanup.')
        after = before['general'] | {'dryRun': False}
        return {'kind': 'live', 'preset': run['preset'], 'intent': run['intent'], 'revision': run['revision'],
                'bindings': run['bindings'], 'snapshot': before, 'parent': key,
                'ops': [{'app': 'cleanuparr', 'key': 'general', 'path': PATHS['general'], 'method': 'PUT', 'before': before['general'], 'after': after}]}

    async def restore_review(self, key):
        run = self.run(key)
        plan = {'kind': 'restore', 'preset': run['preset'], 'revision': self.store.config()[0],
                'bindings': run['bindings'], 'snapshot': await self.snapshot(), 'parent': key, 'ops': []}
        self.check(plan)
        general = plan['snapshot']['general']
        # Restoration always enters/stays in dry-run, including restoration of previously live settings.
        if general['dryRun'] is not True:
            plan['ops'].append({'app': 'cleanuparr', 'key': 'general', 'path': PATHS['general'], 'method': 'PUT',
                                'before': general, 'after': general | {'dryRun': True}})
        for old in reversed(run['ops']):
            current = await self.read_op(old)
            if old['method'] == 'DELETE':
                continue  # Restoring a restore must not silently recreate deleted rules.
            if old['method'] == 'POST':
                if current is None:
                    continue
                expected = old.get('created')
                if (expected is not None and current != expected) or not self.rule_matches(current, old['after']):
                    raise Conflict('A preset rule was edited later. It was preserved; review it in Cleanuparr.')
                path = PATHS['stall'] + '/' + identity(current['id']) if old['key'] == 'stall' else '/api/seeding-rules/' + identity(current['id'])
                plan['ops'].append({**old, 'path': path, 'method': 'DELETE', 'before': current, 'after': None})
                continue
            wanted = copy.deepcopy(old['before'])
            expected = old['after']
            if old['key'] == 'general':
                current = current | {'dryRun': True}
                expected = expected | {'dryRun': True}
                wanted['dryRun'] = True
            if current == wanted:
                continue
            if current != expected:
                raise Conflict('A setting was edited after this preset. It was preserved; review it in the app before restoring.')
            plan['ops'].append({**old, 'method': 'PUT', 'before': current, 'after': wanted})
        return plan
