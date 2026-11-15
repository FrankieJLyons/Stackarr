import copy
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from stackarr.cleanup_presets import ARRS, PATHS, CleanupPresets, Intent
from stackarr.store import Conflict, Store

CLIENT = '11111111-1111-1111-1111-111111111111'


class Apps:
    def __init__(self, store):
        self.store = store
        self.data = json.loads((Path(__file__).parent / 'fixtures/cleanuparr-2.10.11.json').read_text())
        self.data['clients'] = [{'id': CLIENT, 'enabled': True, 'typeName': 'qBittorrent',
                                 'host': 'http://qbittorrent.test:8080', 'urlBase': None, 'password': 'PRIVATE-qbit'}]
        self.data['download_cleaner']['clients'] = [{'downloadClientId': CLIENT, 'downloadClientName': 'Downloads',
            'downloadClientEnabled': True, 'downloadClientTypeName': 'qBittorrent', 'seedingRules': [],
            'unlinkedConfig': None, 'deadTorrentConfig': None, 'orphanedFilesConfig': None}]
        for app in ('sonarr', 'radarr'):
            self.data['arr_' + app]['instances'] = [{'id': str(uuid4()), 'enabled': True, 'url': f'http://{app}.test', 'apiKey': 'PRIVATE-arr'}]
        self.preferences = {'excluded_file_names_enabled': False, 'excluded_file_names': '*.nfo',
                            'autorun_enabled': True, 'autorun_on_torrent_added_enabled': True, 'untouched': 'keep'}
        self.categories = {'sonarr': {}, 'imported-tv': {}}
        self.post_category = 'imported-tv'
        self.writes = []
        self.fail_after = None
        self.before_request = None

    def respond(self, request):
        if self.before_request:
            self.before_request(request)
        host, path, method = request.url.host, request.url.path, request.method
        assert host in ('cleanuparr.test', 'qbittorrent.test', 'sonarr.test', 'radarr.test')
        if host == 'qbittorrent.test':
            if path.endswith('/auth/login'):
                return httpx.Response(200, text='Ok.')
            if method == 'GET':
                data = self.preferences if path.endswith('/preferences') else self.categories if path.endswith('/categories') else []
            else:
                from urllib.parse import parse_qs
                body = json.loads(parse_qs(request.content.decode())['json'][0])
                self.writes.append(('qbit', method, path, body))
                self.preferences.update(body)
                return httpx.Response(200)
        elif host in ('sonarr.test', 'radarr.test'):
            assert method == 'GET'
            app = host.split('.')[0]
            data = {'enableCompletedDownloadHandling': True} if '/config/' in path else [
                {'enable': True, 'implementation': 'QBittorrent', 'fields': [
                    {'name': 'host', 'value': 'qbittorrent.test'}, {'name': 'port', 'value': 8080},
                    {'name': 'tvCategory' if app == 'sonarr' else 'movieCategory', 'value': app},
                    {'name': 'tvImportedCategory' if app == 'sonarr' else 'movieImportedCategory', 'value': self.post_category}]}]
        elif method == 'GET':
            if path == '/api/status':
                data = {'application': {'version': self.data['version']}}
            elif path.startswith('/api/seeding-rules/'):
                data = self.data['download_cleaner']['clients'][0]['seedingRules']
            else:
                key = next(key for key, value in PATHS.items() if value == path)
                data = {'clients': self.data[key]} if key == 'clients' else self.data[key]
        else:
            body = json.loads(request.content) if request.content else None
            self.writes.append(('cleanup', method, path, body))
            if path.startswith('/api/seeding-rules/'):
                rules = self.data['download_cleaner']['clients'][0]['seedingRules']
                if method == 'DELETE':
                    rules[:] = [row for row in rules if row['id'] != path.split('/')[-1]]
                    data = None
                else:
                    data = body | {'id': str(uuid4()), 'priority': 1}
                    rules.append(data)
            elif path.startswith('/api/queue-rules/stall'):
                if method == 'DELETE':
                    self.data['stall'][:] = [row for row in self.data['stall'] if row['id'] != path.split('/')[-1]]
                    data = None
                else:
                    data = body | {'id': str(uuid4())}
                    self.data['stall'].append(data)
                    self.data['stall'].sort(key=lambda row: row['id'])
            else:
                key = next(key for key, value in PATHS.items() if value == path)
                if key == 'queue_cleaner':
                    assert body['failedImport']['maxStrikes'] == 0 or body['failedImport']['patternMode'] != 'Include' or body['failedImport']['patterns']
                if key == 'download_cleaner':
                    assert 'clients' not in body
                    self.data[key].update(body)
                else:
                    self.data[key] = body
                data = {'message': 'saved'}
            if self.fail_after == path:
                self.fail_after = None
                raise httpx.ReadError('Lost response after save')
        return httpx.Response(200, json=copy.deepcopy(data))


def configure(store):
    revision, config = store.config()
    for app in ('cleanuparr', 'qbittorrent', 'sonarr', 'radarr'):
        config.integrations[app].enabled = True
        config.integrations[app].url = f'http://{app}.test' + (':8080' if app == 'qbittorrent' else '')
    store.save(config, revision, {app: {'api_key': 'PRIVATE-api', 'username': 'test', 'password': 'PRIVATE-password'}
                                 for app in ('cleanuparr', 'qbittorrent', 'sonarr', 'radarr')})


@pytest.fixture
def fixture(tmp_path):
    store = Store(tmp_path)
    configure(store)
    apps = Apps(store)
    feature = CleanupPresets(store, httpx.MockTransport(apps.respond))
    return store, apps, feature


def intent(preset):
    return Intent(preset=preset, connectivity_url='https://check.example', client_id=CLIENT, category='imported-tv')


@pytest.mark.parametrize('preset', ['observe', 'media', 'recover', 'completed'])
async def test_review_apply_restore_preserves_connections_and_other_preferences(fixture, preset):
    store, apps, feature = fixture
    original = copy.deepcopy(apps.data)
    prefs = copy.deepcopy(apps.preferences)
    plan = await feature.review(intent(preset))
    assert not apps.writes
    assert 'PRIVATE' not in json.dumps(feature.public(plan)) and 'apiKey' not in json.dumps(feature.public(plan))
    result = await feature.apply(plan)
    assert result['state'] == 'applied', result
    assert apps.data['general']['dryRun'] is True
    assert apps.data['clients'] == original['clients']
    assert all(apps.data['arr_' + key] == original['arr_' + key] for key in ARRS)
    assert apps.preferences['untouched'] == 'keep'
    if preset == 'recover':
        assert apps.data['stall'][0]['privacyType'] == 'Public'
        assert apps.data['stall'][0]['resetStrikesOnProgress'] is True
    if preset == 'completed':
        rule = apps.data['download_cleaner']['clients'][0]['seedingRules'][0]
        assert rule['privacyType'] == 'Public' and rule['maxSeedTime'] == -1
        assert not rule['deleteSourceFiles'] and rule['minSeedTime'] == 72 and rule['maxRatio'] == 2
    restored = CleanupPresets(Store(store.root), feature.transport)
    recovery = await restored.restore_review(result['id'])
    outcome = await restored.apply(recovery)
    assert outcome['state'] == 'applied', outcome
    assert apps.data == original and apps.preferences == prefs
    assert b'PRIVATE' not in store.path.read_bytes()


@pytest.mark.parametrize('preset', ['recover', 'completed'])
async def test_live_is_independent_of_dry_run_apply_and_rechecks_prerequisites(fixture, preset):
    _, apps, feature = fixture
    result = await feature.apply(await feature.review(intent(preset)))
    live = await feature.live_review(result['id'])
    assert apps.data['general']['dryRun'] is True
    assert len(live['ops']) == 1 and live['ops'][0]['after']['dryRun'] is False
    if preset == 'completed':
        apps.post_category = 'somewhere-else'
        with pytest.raises(Conflict):
            await feature.apply(live)
        apps.post_category = 'imported-tv'
    result_live = await feature.apply(live)
    assert result_live['state'] == 'applied' and apps.data['general']['dryRun'] is False
    restored = await feature.apply(await feature.restore_review(result_live['id']))
    assert restored['state'] == 'applied' and apps.data['general']['dryRun'] is True


async def test_observe_and_media_cannot_grant_live_cleanup(fixture):
    _, apps, feature = fixture
    result = await feature.apply(await feature.review(Intent()))
    with pytest.raises(ValueError, match='requires an applied'):
        await feature.live_review(result['id'])
    assert apps.data['general']['dryRun'] is True


async def test_stale_review_unknown_version_and_native_read_only_fail_without_writes(fixture):
    store, apps, feature = fixture
    plan = await feature.review(Intent())
    apps.data['general']['httpTimeout'] += 1
    with pytest.raises(Conflict):
        await feature.apply(plan)
    assert not apps.writes
    apps.data['version'] = '9.0.0'
    with pytest.raises(ValueError, match='verified version'):
        await feature.review(Intent())
    apps.data['version'] = '2.10.11.0'
    plan = await feature.review(Intent())
    revision, config = store.config()
    config.integrations['cleanuparr'].read_only = True
    store.save(config, revision, {})
    with pytest.raises(ValueError, match='read-only'):
        await feature.apply(plan)
    assert not apps.writes


async def test_live_is_rejected_if_jobs_sources_or_categories_change(fixture):
    _, apps, feature = fixture
    result = await feature.apply(await feature.review(intent('recover')))
    apps.data['blacklist_sync']['enabled'] = True
    with pytest.raises(Conflict):
        await feature.live_review(result['id'])
    apps.data['blacklist_sync']['enabled'] = False
    apps.data['arr_sonarr']['instances'][0]['url'] = 'http://foreign.test'
    with pytest.raises(Conflict):
        await feature.live_review(result['id'])


async def test_recovery_rejects_other_download_clients_without_writes(fixture):
    _, apps, feature = fixture
    apps.data['clients'].append({'id': str(uuid4()), 'enabled': True, 'typeName': 'Transmission', 'host': 'http://other.test'})
    assert (await feature.status())['recovery_blocker']
    with pytest.raises(ValueError, match='one matching qBittorrent'):
        await feature.review(intent('recover'))
    assert not apps.writes


async def test_failed_apply_has_durable_recovery_without_blind_retry(fixture):
    store, apps, feature = fixture
    apps.fail_after = '/api/queue-rules/stall'
    result = await feature.apply(await feature.review(intent('recover')))
    assert result['state'] == 'uncertain'
    assert feature.history()[0]['id'] == result['id'] and apps.data['general']['dryRun']
    restored = CleanupPresets(Store(store.root), feature.transport)
    result = await restored.apply(await restored.restore_review(result['id']))
    assert result['state'] == 'applied' and not apps.data['stall']


async def test_restore_preserves_later_edits_and_never_restores_live_mode(fixture):
    _, apps, feature = fixture
    apps.data['general']['dryRun'] = False
    result = await feature.apply(await feature.review(Intent()))
    apps.data['queue_cleaner']['errored']['maxStrikes'] = 99
    with pytest.raises(Conflict, match='edited after'):
        await feature.restore_review(result['id'])
    apps.data['queue_cleaner']['errored']['maxStrikes'] = 6
    assert (await feature.apply(await feature.restore_review(result['id'])))['state'] == 'applied'
    assert apps.data['general']['dryRun'] is True


async def test_completed_requires_a_separate_import_category_and_preserves_existing_rules(fixture):
    _, apps, feature = fixture
    apps.post_category = 'sonarr'
    assert not (await feature.status())['imported_categories']
    with pytest.raises(ValueError, match='verified post-import'):
        await feature.review(intent('completed'))
    apps.post_category = 'imported-tv'
    apps.data['download_cleaner']['clients'][0]['seedingRules'] = [{'id': str(uuid4()), 'name': 'User rule'}]
    with pytest.raises(ValueError, match='already has rules'):
        await feature.review(intent('completed'))
    assert not apps.writes


def test_routes_require_session_csrf_one_use_and_separate_live_confirmation(client, app, auth):
    configure(app.state.store)
    apps = Apps(app.state.store)
    feature = app.state.cleanup_presets
    feature.transport = httpx.MockTransport(apps.respond)
    feature.http.transport = feature.transport
    feature.protection.transport = feature.transport
    assert client.post('/api/cleanuparr-presets/review', json={}).status_code == 403
    preview = client.post('/api/cleanuparr-presets/review', headers=auth, json=intent('recover').model_dump())
    assert preview.status_code == 200 and 'PRIVATE' not in preview.text
    token = {'review_token': preview.json()['review_token']}
    result = client.post('/api/cleanuparr-presets/apply', headers=auth, json=token)
    assert result.status_code == 200 and result.json()['state'] == 'applied'
    assert client.post('/api/cleanuparr-presets/apply', headers=auth, json=token).status_code == 409
    live = client.post('/api/cleanuparr-presets/live/review', headers=auth, json={'run_id': result.json()['id']}).json()
    token = {'review_token': live['review_token']}
    assert client.post('/api/cleanuparr-presets/apply', headers=auth, json=token).status_code == 409
    assert client.post('/api/cleanuparr-presets/live/apply', headers=auth, json=token).status_code == 422
    token.update(confirmation='ENABLE LIVE DELETION', acknowledge_irreversible=False)
    assert client.post('/api/cleanuparr-presets/live/apply', headers=auth, json=token).status_code == 422
    assert apps.data['general']['dryRun'] is True
    token['acknowledge_irreversible'] = 1
    assert client.post('/api/cleanuparr-presets/live/apply', headers=auth, json=token).status_code == 422
    token['acknowledge_irreversible'] = True
    assert client.post('/api/cleanuparr-presets/live/apply', headers=auth, json=token).json()['state'] == 'applied'
    assert client.post('/api/cleanuparr-presets/live/apply', headers=auth, json=token).status_code == 409
    client.post('/api/logout', headers=auth)
    assert client.get('/api/cleanuparr-presets').status_code == 401
    assert client.post('/api/cleanuparr-presets/live/review', headers=auth, json={'run_id': result.json()['id']}).status_code == 401


def test_review_is_bound_to_the_browser_session(client, app, auth):
    from fastapi.testclient import TestClient
    configure(app.state.store)
    apps = Apps(app.state.store)
    feature = app.state.cleanup_presets
    feature.http.transport = feature.transport = httpx.MockTransport(apps.respond)
    preview = client.post('/api/cleanuparr-presets/review', headers=auth, json={}).json()
    with TestClient(app) as second:
        origin = {'Origin': 'http://testserver'}
        login = second.post('/api/login', headers=origin, json={'password': 'synthetic test password'}).json()
        headers = origin | {'X-CSRF-Token': login['csrf']}
        assert second.post('/api/cleanuparr-presets/apply', headers=headers,
                           json={'review_token': preview['review_token']}).status_code == 409
    assert not apps.writes
