"""Reviewed qBittorrent hardening. Filename exclusions are not malware scanning."""

import json
import secrets
import time
from contextlib import asynccontextmanager

import httpx
from pydantic import Field

from .adapters import require_write
from .config import Model, container_port
from .integrations import IntegrationError, bounded_response
from .native_import import require_writable
from .store import Conflict

EXECUTABLES = ('exe', 'com', 'scr', 'msi', 'msp', 'bat', 'cmd', 'ps1', 'psm1', 'vbs', 'vbe',
               'js', 'jse', 'wsf', 'wsh', 'hta', 'lnk', 'scf', 'url', 'dll', 'jar', 'sh', 'py',
               'app', 'desktop')
ARCHIVES = ('zip', 'zipx', 'rar', '7z', 'iso', 'img', 'gz', 'bz2', 'xz', 'tar', '001', 'r[0-9][0-9]')
KEYS = ('excluded_file_names_enabled', 'excluded_file_names', 'autorun_enabled', 'autorun_on_torrent_added_enabled')
NOTICE = ('Applies to newly added torrents once their filenames are known. Existing torrents are not changed. '
          'Filename exclusions are not antivirus: disguised files, malicious media and shared torrent pieces can still '
          'contain harmful bytes. Keep your operating system and players updated; never run files from a download.')


class ProtectionIntent(Model):
    block_archives: bool = Field(default=True, strict=True)


def binding(store, app):
    return {'integration': store.config()[1].integrations[app].model_dump(), 'credential': store.secret(app)}


def address(store, app):
    value = store.config()[1].integrations[app]
    if not value.enabled:
        raise ValueError('Connect ' + app + ' in Apps first.')
    return value.url or f'http://{app}:{container_port(app, value)}'


async def request(client, method, url, *, raw=False, **kwargs):
    try:
        response, content = await bounded_response(client, method, url, **kwargs)
        if not response.is_success:
            raise ValueError('An app rejected the request. Check its saved connection and review again.')
        return (response, content) if raw else content
    except (httpx.HTTPError, IntegrationError):
        raise ValueError('An app did not respond. Check its connection and review again; a sent change may need checking.') from None


class Qbit:
    def __init__(self, client, base):
        self.client, self.base = client, base

    async def get(self, tail):
        data = await request(self.client, 'GET', self.base + '/api/v2/' + tail)
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError('qBittorrent returned unsupported settings.') from None

    async def post(self, tail, data):
        await request(self.client, 'POST', self.base + '/api/v2/' + tail, data=data)


@asynccontextmanager
async def qbit_client(store, transport=None):
    base, credential = address(store, 'qbittorrent'), store.secret('qbittorrent')
    if not credential.get('username') or not credential.get('password'):
        raise ValueError('Save the qBittorrent login in Apps first.')
    async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, timeout=8,
                                headers={'Referer': base + '/'}) as client:
        response, reply = await request(client, 'POST', base + '/api/v2/auth/login', raw=True, data={
            'username': credential['username'], 'password': credential['password']})
        if response.status_code != 204 and reply.strip() != b'Ok.':
            raise ValueError('qBittorrent did not accept its saved login.')
        yield Qbit(client, base)


def selected(preferences):
    if (not isinstance(preferences, dict) or any(type(preferences.get(key)) is not bool for key in KEYS if key != 'excluded_file_names')
            or not isinstance(preferences.get('excluded_file_names'), str) or len(preferences['excluded_file_names']) > 32000):
        raise ValueError('This qBittorrent version does not expose supported exclusion and automatic-program settings. Update it before enabling protection.')
    return {key: preferences[key] for key in KEYS}


def proposed(before, archives):
    patterns = before['excluded_file_names'].splitlines()
    existing = {item.casefold() for item in patterns}
    for extension in EXECUTABLES + (ARCHIVES if archives else ()):
        for item in ('*.' + extension, '*.' + extension + '.*'):
            if item.casefold() not in existing:
                patterns.append(item)
                existing.add(item.casefold())
    return {'excluded_file_names_enabled': True, 'excluded_file_names': '\n'.join(patterns),
            'autorun_enabled': False, 'autorun_on_torrent_added_enabled': False}


class Protection:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport

    async def cleanup(self):
        app = self.store.config()[1].integrations['cleanuparr']
        if not app.enabled:
            return 'Cleanuparr is optional. qBittorrent enforces these exclusions itself.'
        key = self.store.secret('cleanuparr').get('api_key')
        if not key:
            raise ValueError('Connect Cleanuparr first so Stackarr can check whether its blacklist sync would replace these exclusions.')
        async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False,
                                    timeout=8, headers={'X-Api-Key': key}) as client:
            raw = await request(client, 'GET', address(self.store, 'cleanuparr') + '/api/configuration/blacklist_sync')
        try:
            config = json.loads(raw)
            if config['enabled'] is not False:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ValueError('Cleanuparr blacklist sync may replace qBittorrent exclusions. Turn that job off in Cleanuparr or manage the list there, then check again.') from None
        return 'Cleanuparr blacklist sync is off. Its cleanup and deletion settings are preserved.'

    async def review(self, intent):
        revision = self.store.config()[0]
        bound = {key: binding(self.store, key) for key in ('qbittorrent', 'cleanuparr')}
        cleanup = await self.cleanup()
        async with qbit_client(self.store, self.transport) as client:
            before = selected(await client.get('app/preferences'))
            torrents = await client.get('torrents/info?limit=1000')
        if not isinstance(torrents, list):
            raise ValueError('The existing download queue could not be checked.')
        return {'revision': revision, 'bindings': bound, 'before': before, 'after': proposed(before, intent.block_archives),
                'archives': intent.block_archives, 'existing': len(torrents), 'cleanup': cleanup}

    @staticmethod
    def public(plan):
        return {'block_archives': plan['archives'], 'existing_downloads': plan['existing'],
                'existing_patterns': len(plan['before']['excluded_file_names'].splitlines()),
                'programs_were_enabled': plan['before']['autorun_enabled'] or plan['before']['autorun_on_torrent_added_enabled'],
                'changed': plan['before'] != plan['after'], 'notice': NOTICE, 'cleanup': plan['cleanup'],
                'patterns': plan['after']['excluded_file_names'].splitlines()}

    def check(self, plan):
        require_writable(self.store, 'qbittorrent')
        if (self.store.config()[0] != plan['revision'] or
                any(binding(self.store, key) != value for key, value in plan['bindings'].items())):
            raise Conflict('Connections changed. Review download protection again.')

    def save(self, identity, run):
        # Lazy on explicit write only: read-only upgrade checks must not change the database schema.
        with self.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS download_protection_runs (id TEXT PRIMARY KEY, created REAL, value BLOB)')
            db.execute('INSERT INTO download_protection_runs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (identity, time.time(), self.store.cipher.encrypt(json.dumps(run).encode())))

    def history(self):
        with self.store.db() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='download_protection_runs'").fetchone()
            rows = db.execute('SELECT id,created,value FROM download_protection_runs ORDER BY created DESC LIMIT 20').fetchall() if exists else []
        return [{'id': row[0], 'created': row[1], 'state': json.loads(self.store.cipher.decrypt(row[2]))['state']} for row in rows]

    async def apply(self, plan):
        self.check(plan)
        require_write('qbittorrent', 'protection.configure')
        await self.cleanup()
        async with qbit_client(self.store, self.transport) as client:
            if selected(await client.get('app/preferences')) != plan['before']:
                raise Conflict('Download settings changed. Preview protection again.')
            self.check(plan)
            if plan['before'] == plan['after']:
                return {'message': 'The reviewed exclusions and automatic-program settings are already in place.', 'state': 'unchanged'}
            identity, run = secrets.token_hex(16), {**plan, 'state': 'applying'}
            self.save(identity, run)
            try:
                await client.post('app/setPreferences', {'json': json.dumps(plan['after'])})
                if selected(await client.get('app/preferences')) != plan['after']:
                    raise ValueError('The exclusion settings did not verify.')
                self.check(plan)
                run['state'] = 'applied'
            except (ValueError, Conflict):
                run['state'] = 'uncertain'
            self.save(identity, run)
        self.store.audit('download-protection.' + run['state'], 'qbittorrent')
        return {'id': identity, 'state': run['state'], 'message': 'Download protection saved and verified. ' + NOTICE if run['state'] == 'applied'
                else 'The save could not be verified. Check protection again; the saved recovery record can restore unchanged settings.'}

    async def undo(self, identity):
        with self.store.db() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='download_protection_runs'").fetchone()
            row = db.execute('SELECT value FROM download_protection_runs WHERE id=?', (identity,)).fetchone() if exists else None
        if not row:
            raise ValueError('Choose a saved protection change.')
        run = json.loads(self.store.cipher.decrypt(row[0]))
        # Later unrelated Stackarr settings need not prevent recovery; actual app bindings must still match.
        run['revision'] = self.store.config()[0]
        self.check(run)
        require_write('qbittorrent', 'protection.configure')
        await self.cleanup()
        async with qbit_client(self.store, self.transport) as client:
            current = selected(await client.get('app/preferences'))
            if current != run['before']:
                if current != run['after'] or run['state'] == 'restored':
                    raise Conflict('These settings were edited after Stackarr saved them. Your edits are preserved.')
                run['state'] = 'restoring'
                self.save(identity, run)
                self.check(run)
                await client.post('app/setPreferences', {'json': json.dumps(run['before'])})
                if selected(await client.get('app/preferences')) != run['before']:
                    raise ValueError('Restore could not be verified. Check the app and retry recovery.')
            run['state'] = 'restored'
            self.save(identity, run)
        return {'id': identity, 'state': 'restored', 'message': 'The previous filename exclusions and automatic-program settings were restored.'}
