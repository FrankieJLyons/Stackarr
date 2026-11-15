import copy
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from stackarr.download_protection import Protection, ProtectionIntent, proposed, selected
from stackarr.home import Home, HomeError
from stackarr.library_mapping import LibraryMapping, MappingIntent, translated
from stackarr.native_import import connect
from stackarr.native_plex import inspect as inspect_plex
from stackarr.server import create_app
from stackarr.storage_topology import direct_directory, host_folder, posix
from stackarr.store import Conflict, Store
from tests.test_controller_dashboard import authorize


class Apps:
    def __init__(self, store):
        self.store = store
        self.prefs = {'excluded_file_names_enabled': False, 'excluded_file_names': '*.nfo',
                      'autorun_enabled': True, 'autorun_on_torrent_added_enabled': True,
                      'use_category_paths_in_manual_mode': False, 'auto_tmm_enabled': False,
                      'autorun_program': 'PRIVATE-command', 'web_ui_password': 'PRIVATE-password', 'save_path': '/unchanged'}
        self.categories = {key: {'name': key, 'savePath': '/data/downloads/' + key} for key in ('sonarr', 'radarr')}
        self.sections = [{'key': '1', 'type': 'show', 'title': 'TV', 'Location': [{'path': '/plex/tv'}]},
                         {'key': '2', 'type': 'movie', 'title': 'Movies', 'Location': [{'path': '/plex/movies'}]}]
        self.roots = [{'id': 1, 'path': '/data/media/tv', 'accessible': True, 'freeSpace': 10}]
        self.clients = [{'id': 1, 'name': 'existing', 'enable': True, 'implementation': 'QBittorrent', 'fields': [
            {'name': 'host', 'value': 'qbittorrent'}, {'name': 'port', 'value': 8080},
            {'name': 'tvCategory', 'value': 'sonarr'}, {'name': 'password', 'value': 'PRIVATE-qbit-secret'}]}]
        self.handling = {'id': 1, 'enableCompletedDownloadHandling': True, 'unrelated': 123}
        self.notifications = [{'id': 1, 'implementation': 'PlexServer', 'name': 'My existing connection'}]
        self.queue = {'totalRecords': 0, 'records': []}
        self.claimed = True
        self.sync = False
        self.torrents = []
        self.writes = []
        self.lost = False
        self.bad_test = False
        self.topology = {'folders': {'/plex/tv': 'C:/Media/media/tv'}, 'case_sensitive': False,
                         'apps': [{'app': app, 'port': port, 'id': app + '-owned', 'downloads': {
                             'sonarr': {'path': '/data/downloads/sonarr', 'host': 'C:/Media/downloads/sonarr'}},
                             'mounts': [{'source': 'C:/Media', 'target': '/data', 'writable': True}]}
                                  for app, port in [('plex', 42401), ('sonarr', 18990), ('qbittorrent', 18080)]]}

    async def probe(self, query):
        assert query == {'plex_port': 42401, 'folders': ['/plex/tv']}
        return copy.deepcopy(self.topology)

    def respond(self, request):
        path, method = request.url.path, request.method
        if path == '/api/v2/auth/login':
            return httpx.Response(204, headers={'Set-Cookie': 'SID=private-fixture; HttpOnly'})
        if path == '/api/v3/downloadclient/test':
            return httpx.Response(200, json=[])
        if path == '/api/v3/notification/test':
            return httpx.Response(400 if self.bad_test else 200, json=[])
        if method != 'GET':
            assert not self.store.config()[1].integrations['sonarr'].read_only or request.url.port == 18080
            self.writes.append((method, path, request.content))
            with self.store.db() as db:
                assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('download_protection_runs','library_mapping_runs')").fetchone()[0]
            if path == '/api/v2/app/setPreferences':
                self.prefs.update(json.loads(parse_qs(request.content.decode())['json'][0]))
                if self.lost:
                    self.lost = False
                    raise httpx.ReadError('Lost response after successful save')
                return httpx.Response(204)
            if path == '/api/v3/config/downloadclient/1':
                self.handling = json.loads(request.content)
                return httpx.Response(202, json=self.handling)
            if path == '/api/v3/rootfolder':
                row = json.loads(request.content) | {'id': 22, 'accessible': True}
                self.roots.append(row)
                return httpx.Response(201, json=row)
            if path == '/api/v3/notification':
                row = json.loads(request.content) | {'id': 22}
                self.notifications.append(row)
                return httpx.Response(201, json=row)
            raise AssertionError((method, path))
        data = {
            '/api/v2/app/preferences': self.prefs, '/api/v2/torrents/info': self.torrents,
            '/api/v2/torrents/categories': self.categories, '/api/v3/rootfolder': self.roots,
            '/api/v3/downloadclient': self.clients, '/api/v3/config/downloadclient': self.handling,
            '/api/v3/notification': self.notifications, '/api/v3/queue': self.queue,
            '/api/v3/notification/22': self.notifications[-1] if self.notifications else {},
            '/api/v3/notification/schema': [{'implementation': 'PlexServer', 'configContract': 'PlexServerSettings',
                'supportsOnDownload': True, 'supportsOnUpgrade': True, 'supportsOnImportComplete': True,
                'fields': [{'name': key, 'value': None} for key in ('host', 'port', 'useSsl', 'authToken', 'updateLibrary', 'mapFrom', 'mapTo', 'urlBase')]}],
            '/identity': {'MediaContainer': {'claimed': self.claimed, 'machineIdentifier': 'native-machine', 'version': '1.43'}},
            '/library/sections': {'MediaContainer': {'Directory': self.sections}},
            '/api/configuration/blacklist_sync': {'enabled': self.sync},
            '/api/v1/settings/sonarr': [{'id': 1, 'hostname': 'sonarr', 'port': 8989, 'apiKey': 'PRIVATE-sonarr'}],
        }[path]
        return httpx.Response(200, json=copy.deepcopy(data))


@pytest.fixture
def media(tmp_path):
    store = Store(tmp_path)
    revision, config = store.config()
    credentials = {}
    for app, port, peer in [('qbittorrent', 18080, 8080), ('sonarr', 18990, 8989), ('plex', 42401, 32400), ('seerr', 15055, 5055)]:
        config.integrations[app].enabled = True
        config.integrations[app].url = f'http://127.0.0.1:{port}'
        config.integrations[app].peer_url = f'http://{app}:{peer}'
        credentials[app] = {'api_key': 'PRIVATE-' + app} if app != 'qbittorrent' else {'username': 'admin', 'password': 'PRIVATE-qbit-secret'}
    store.save(config, revision, credentials)
    apps = Apps(store)
    transport = httpx.MockTransport(apps.respond)
    return store, apps, Protection(store, transport), LibraryMapping(store, apps.probe, transport), transport


@pytest.mark.asyncio
async def test_protection_retains_user_patterns_writes_only_four_fields_and_can_restore(media):
    store, apps, protection, _, _ = media
    before = copy.deepcopy(apps.prefs)
    plan = await protection.review(ProtectionIntent())
    public = protection.public(plan)
    assert 'PRIVATE' not in json.dumps(public)
    assert '*.nfo' in public['patterns'] and '*.exe' in public['patterns'] and '*.rar' in public['patterns']
    result = await protection.apply(plan)
    assert result['state'] == 'applied'
    assert apps.prefs['save_path'] == before['save_path'] and apps.prefs['autorun_program'] == before['autorun_program']
    assert not apps.prefs['autorun_enabled'] and apps.prefs['excluded_file_names_enabled']
    assert b'PRIVATE-' not in store.path.read_bytes()
    assert (await protection.undo(result['id']))['state'] == 'restored'
    assert apps.prefs == before


@pytest.mark.asyncio
async def test_protection_recovers_a_lost_response_after_restart(media):
    store, apps, protection, _, transport = media
    before = copy.deepcopy(apps.prefs)
    plan = await protection.review(ProtectionIntent(block_archives=False))
    assert '*.rar' not in protection.public(plan)['patterns']
    apps.lost = True
    result = await protection.apply(plan)
    assert result['state'] == 'uncertain'
    fresh = Protection(store, transport)
    assert fresh.history()[0]['state'] == 'uncertain'
    await fresh.undo(result['id'])
    assert apps.prefs == before


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['settings', 'connection', 'credential', 'read-only'])
async def test_protection_rejects_changed_state_before_writing(media, change):
    store, apps, protection, _, _ = media
    plan = await protection.review(ProtectionIntent())
    if change == 'settings':
        apps.prefs['excluded_file_names'] += '\n*.txt'
    else:
        rev, cfg = store.config()
        if change == 'read-only':
            cfg.integrations['qbittorrent'].read_only = True
        if change == 'connection':
            cfg.integrations['qbittorrent'].url = 'http://127.0.0.1:9999'
        store.save(cfg, rev, {'qbittorrent': {'username': 'changed', 'password': 'changed'}} if change == 'credential' else {})
    with pytest.raises((ValueError, Conflict)):
        await protection.apply(plan)
    assert not apps.writes


@pytest.mark.asyncio
async def test_protection_restore_preserves_later_edits(media):
    _, apps, protection, _, _ = media
    result = await protection.apply(await protection.review(ProtectionIntent()))
    apps.prefs['excluded_file_names'] += '\n*.later'
    count = len(apps.writes)
    with pytest.raises(Conflict):
        await protection.undo(result['id'])
    assert len(apps.writes) == count


@pytest.mark.asyncio
async def test_blacklist_sync_conflict_blocks_protection(media):
    store, apps, protection, _, _ = media
    rev, cfg = store.config()
    cfg.integrations['cleanuparr'].enabled = True
    cfg.integrations['cleanuparr'].url = 'http://127.0.0.1:21012'
    store.save(cfg, rev, {'cleanuparr': {'api_key': 'PRIVATE-cleanup'}})
    apps.sync = True
    with pytest.raises(ValueError, match='replace'):
        await protection.review(ProtectionIntent())
    assert not apps.writes


def test_unsupported_protection_schema_is_not_overwritten():
    with pytest.raises(ValueError, match='version'):
        selected({'excluded_file_names': ''})
    before = {'excluded_file_names': '*.EXE\nmy custom pattern', 'excluded_file_names_enabled': True,
              'autorun_enabled': False, 'autorun_on_torrent_added_enabled': False}
    assert proposed(before, False)['excluded_file_names'].casefold().splitlines().count('*.exe') == 1


@pytest.mark.asyncio
async def test_mapping_detects_unique_library_translates_shared_mounts_and_verifies_request(media):
    _, apps, _, mapping, _ = media
    plan = await mapping.review(MappingIntent(app='sonarr'))
    assert plan['root'] == '/data/media/tv' and plan['staging'] == '/data/downloads/sonarr'
    assert plan['enable_category_paths'] and not plan['create_root']
    assert 'PRIVATE' not in json.dumps(mapping.public(plan))
    result = await mapping.apply(plan)
    assert result['state'] == 'applied'
    assert apps.prefs['use_category_paths_in_manual_mode'] is True
    assert apps.prefs['auto_tmm_enabled'] is False
    assert await mapping.request_root('sonarr', {'id': 1}) == '/data/media/tv'
    assert not any('/torrent' in path or '/movie' in path or '/series' in path for _, path, _ in apps.writes)
    mapping.pause('sonarr')
    assert await mapping.request_root('sonarr', {'id': 1}) is None


@pytest.mark.asyncio
async def test_mapping_adds_missing_root_and_enables_imports_only_for_empty_queue(media):
    _, apps, _, mapping, _ = media
    apps.roots = []
    apps.handling['enableCompletedDownloadHandling'] = False
    plan = await mapping.review(MappingIntent(app='sonarr'))
    assert (await mapping.apply(plan))['state'] == 'applied'
    assert apps.roots[0]['path'] == '/data/media/tv' and apps.handling['unrelated'] == 123


@pytest.mark.asyncio
async def test_mapping_requires_library_choice_with_multiple_folders(media):
    _, apps, _, mapping, _ = media
    apps.sections[0]['Location'].append({'path': '/plex/other-tv'})
    result = await mapping.review(MappingIntent(app='sonarr'))
    assert result['needs_choice'] and len(result['choices']) == 2
    assert not apps.writes


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['mount', 'library', 'credential', 'category', 'client', 'native', 'root'])
async def test_mapping_stale_or_native_review_never_writes(media, changed):
    store, apps, _, mapping, _ = media
    plan = await mapping.review(MappingIntent(app='sonarr'))
    if changed == 'mount':
        apps.topology['apps'][1]['id'] = 'replacement'
    elif changed == 'library':
        apps.sections[0]['title'] = 'changed'
    elif changed == 'category':
        apps.categories['sonarr']['savePath'] = '/other'
    elif changed == 'client':
        apps.clients[0]['enable'] = False
    elif changed == 'root':
        apps.roots[0]['path'] = '/elsewhere'
    else:
        rev, cfg = store.config()
        if changed == 'native':
            cfg.integrations['sonarr'].read_only = True
        store.save(cfg, rev, {'sonarr': {'api_key': 'replacement'}} if changed == 'credential' else {})
    with pytest.raises((ValueError, Conflict)):
        await mapping.apply(plan)
    assert not apps.writes


@pytest.mark.asyncio
async def test_mapping_blocks_unsafe_layouts_and_queue(media):
    _, apps, _, mapping, _ = media
    apps.handling['enableCompletedDownloadHandling'] = False
    apps.queue = {'totalRecords': 1, 'records': [{'downloadId': 'do-not-import'}]}
    with pytest.raises(ValueError, match='queued'):
        await mapping.review(MappingIntent(app='sonarr'))
    apps.queue = {'totalRecords': 0, 'records': []}
    apps.topology['folders']['/plex/tv'] = 'D:/Unshared/tv'
    with pytest.raises(ValueError, match='share'):
        await mapping.review(MappingIntent(app='sonarr'))
    apps.topology['folders']['/plex/tv'] = 'C:/Media/downloads'
    with pytest.raises(ValueError, match='separate'):
        await mapping.review(MappingIntent(app='sonarr'))
    assert not apps.writes


@pytest.mark.asyncio
async def test_mapping_refuses_unclaimed_plex(media):
    _, apps, _, mapping, _ = media
    apps.claimed = False
    with pytest.raises(ValueError, match='claiming'):
        await mapping.review(MappingIntent(app='sonarr'))


@pytest.mark.asyncio
async def test_mapping_request_does_not_fall_back_after_storage_drift(media):
    _, apps, _, mapping, _ = media
    await mapping.apply(await mapping.review(MappingIntent(app='sonarr')))
    apps.topology['apps'][0]['id'] = 'new-server'
    with pytest.raises(ValueError, match='changed'):
        await mapping.request_root('sonarr', {'id': 1})


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['add', 'remove', 'move-selected', 'remove-selected'])
async def test_mapping_request_ignores_unrelated_libraries_but_preserves_selected_folder(media, change):
    _, apps, _, mapping, _ = media
    await mapping.apply(await mapping.review(MappingIntent(app='sonarr')))
    apps.writes.clear()
    if change == 'add':
        apps.sections.append({'key': '3', 'type': 'show', 'title': 'Codec tests',
                              'Location': [{'path': '/plex/test-patterns'}]})
    elif change == 'remove':
        apps.sections.pop(1)
    elif change == 'move-selected':
        apps.sections[0]['Location'][0]['path'] = '/plex/different-tv'
    else:
        apps.sections.pop(0)
    if change in {'add', 'remove'}:
        assert await mapping.request_root('sonarr', {'id': 1}) == '/data/media/tv'
    else:
        with pytest.raises(ValueError, match='libraries or media mounts changed'):
            await mapping.request_root('sonarr', {'id': 1})
    assert not apps.writes


@pytest.mark.asyncio
async def test_mapping_notification_uses_verified_path_translation_without_delete_triggers(media):
    _, apps, _, mapping, _ = media
    apps.notifications = []
    plan = await mapping.review(MappingIntent(app='sonarr'))
    assert (await mapping.apply(plan))['state'] == 'applied'
    created = apps.notifications[0]
    fields = {row['name']: row['value'] for row in created['fields']}
    assert fields['mapFrom'] == '/data/media/tv' and fields['mapTo'] == '/plex/tv'
    assert created['onDownload'] and created['onUpgrade'] and not created['onGrab']
    assert not any(key.startswith('onDelete') for key in created)


@pytest.mark.asyncio
async def test_failed_notification_test_leaves_recoverable_partial_setup(media):
    _, apps, _, mapping, _ = media
    apps.notifications = []
    apps.bad_test = True
    result = await mapping.apply(await mapping.review(MappingIntent(app='sonarr')))
    assert result['state'] == 'needs-review' and not apps.notifications
    with pytest.raises(ValueError, match='Review'):
        await mapping.request_root('sonarr', {'id': 1})
    apps.bad_test = False
    assert (await mapping.apply(await mapping.review(MappingIntent(app='sonarr'))))['state'] == 'applied'


@pytest.mark.asyncio
async def test_mapping_request_rechecks_category_before_sending_to_seerr(media):
    _, apps, _, mapping, _ = media
    await mapping.apply(await mapping.review(MappingIntent(app='sonarr')))
    apps.categories['sonarr']['savePath'] = '/do-not-use'
    with pytest.raises(ValueError, match='staging'):
        await mapping.request_root('sonarr', {'id': 1})


def test_mapping_paths_use_host_semantics_and_reject_traversal(tmp_path):
    record = {'mounts': [{'source': 'C:/Media', 'target': '/data', 'writable': True}]}
    assert translated(record, 'c:/media/TV') == '/data/TV'
    with pytest.raises(ValueError):
        translated(record, 'C:/Media2/TV')
    record['mounts'].append({'source': 'D:/Foreign', 'target': '/data/TV', 'writable': True})
    with pytest.raises(ValueError, match='nested'):
        translated(record, 'C:/Media/TV')
    for path in ('/data/../elsewhere', '../data', 'C:\\Media', '/data\x00'):
        with pytest.raises(ValueError):
            posix(path)
    folder = tmp_path / 'media'
    folder.mkdir()
    assert Path(host_folder([{'source': str(tmp_path), 'target': '/data'}], '/data/media')) == folder
    (folder / 'file').write_text('not a directory')
    with pytest.raises(ValueError):
        direct_directory(folder / 'file')


@pytest.mark.asyncio
async def test_native_plex_import_is_read_only_identity_bound_and_private(tmp_path, media):
    _, apps, _, _, transport = media
    source = {'key': 'native_PRIVATE-token', 'machine': 'native-machine', 'address': 'http://127.0.0.1:32400'}
    bundle = await inspect_plex(transport, source_reader=lambda: source.copy())
    assert len(bundle['snapshot']['root_folders']) == 2 and 'native_PRIVATE' not in json.dumps(bundle['snapshot'])
    store = Store(tmp_path / 'imported')
    from stackarr import onboarding

    onboarding.initialize(store)
    await connect(store, bundle, 1, bundle['snapshot'], transport=transport)
    assert store.config()[1].integrations['plex'].read_only and not apps.writes
    with pytest.raises(ValueError, match='match'):
        await inspect_plex(transport, source_reader=lambda: source | {'machine': 'wrong-machine'})


@pytest.mark.asyncio
async def test_native_plex_does_not_block_requests_to_separate_arr_but_keeps_account_writes_blocked(media):
    store, _, _, _, _ = media
    rev, cfg = store.config()
    cfg.integrations['plex'].read_only = True
    store.save(cfg, rev)
    calls = []

    def reply(request):
        calls.append(request)
        assert request.url.port == 15055 and request.url.path == '/api/v1/request'
        return httpx.Response(201, json={'id': 1})

    home = Home(store, httpx.MockTransport(reply))
    assert await home.call('/api/v1/request', 'POST', body={}) == {'id': 1}
    with pytest.raises(HomeError, match='read-only'):
        await home.call('/api/v1/settings/plex', 'POST', body={})
    assert len(calls) == 1


def test_media_routes_session_binding_single_use_csrf_and_no_schema_on_reads(tmp_path, media):
    store, apps, _, _, transport = media
    app = create_app(store.root, origin='http://testserver', transport=transport, background=False, storage_probe=apps.probe)
    with TestClient(app) as client:
        assert client.post('/api/download-protection/review', headers={'Origin': 'http://testserver'}, json={}).status_code == 401
        headers = authorize(client, app)
        assert client.post('/api/download-protection/review', json={}).status_code == 403
        assert client.get('/api/download-protection/history').json() == {'history': []}
        client.get('/api/library-mapping')
        with store.db() as db:
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('download_protection_runs','library_mapping_runs')").fetchone()
        preview = client.post('/api/download-protection/review', headers=headers, json={})
        assert preview.status_code == 200, preview.text
        token = preview.json()['review_token']
        result = client.post('/api/download-protection/apply', headers=headers, json={'review_token': token})
        assert result.status_code == 200 and result.json()['state'] == 'applied'
        assert client.post('/api/download-protection/apply', headers=headers, json={'review_token': token}).status_code == 409
        with TestClient(app) as other:
            assert other.post('/api/library-mapping/apply', headers={'Origin': 'http://testserver'}, json={'review_token': token}).status_code == 401
