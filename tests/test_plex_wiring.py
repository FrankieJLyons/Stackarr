import json

import httpx
import pytest

from stackarr.config import Config
from stackarr.plex_wiring import JOB, SCHEDULE, apply, build
from stackarr.store import Conflict, Store
from stackarr.wiring import public_plan


@pytest.fixture
def refresh_store(tmp_path):
    store = Store(tmp_path)
    config = Config()
    for key in ('plex', 'sonarr', 'radarr', 'seerr'):
        config.integrations[key].enabled = True
        config.integrations[key].url = 'http://' + key + '.test'
    store.save(config, 1, {key: {'api_key': 'private-' + key} for key in ('plex', 'sonarr', 'radarr', 'seerr')})
    return store


class Upstream:
    def __init__(self):
        self.calls = []
        self.rows = {'sonarr': [], 'radarr': []}
        self.machine = 'expected-test-server'
        self.schedule = '0 */5 * * * *'
        self.enabled = ['1', '2']
        self.fail_test = False
        self.auth_error = False
        self.after_test = None
        self.mask_tokens = False
        self.claimed = True
        self.extra_libraries = []

    def response(self, request):
        self.calls.append((request.method, request.url.host, request.url.path))
        host = request.url.host.split('.')[0]
        path = request.url.path
        if host == 'plex':
            assert request.headers['X-Plex-Token'] == 'private-plex'
            if self.auth_error:
                return httpx.Response(401)
            if path == '/identity':
                return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': self.machine, 'claimed': self.claimed}})
            return httpx.Response(200, json={'MediaContainer': {'size': 2, 'Directory': [
                {'key': '1', 'type': 'movie', 'Location': [{'path': '/data/media/movies'}]},
                {'key': '2', 'type': 'show', 'Location': [{'path': '/data/media/tv'}]},
            ] + self.extra_libraries}})
        assert request.headers['X-Api-Key'] == 'private-' + host
        if host == 'seerr':
            if path.endswith('/plex'):
                return httpx.Response(200, json={'machineId': 'expected-test-server', 'libraries': [
                    {'id': key, 'enabled': key in self.enabled} for key in ['1', '2']]})
            if request.method == 'POST':
                self.schedule = json.loads(request.content)['schedule']
            return httpx.Response(200, json=[{'id': JOB, 'cronSchedule': self.schedule}])
        if path.endswith('/rootfolder'):
            return httpx.Response(200, json=[{'path': '/data/media/' + ('tv' if host == 'sonarr' else 'movies')}])
        if path.endswith('/schema'):
            return httpx.Response(200, json=[{'implementation': 'PlexServer', 'configContract': 'PlexServerSettings',
                'supportsOnDownload': True, 'supportsOnUpgrade': True, 'supportsOnImportComplete': host == 'sonarr',
                'fields': [{'name': name, 'value': None} for name in ('host', 'port', 'authToken', 'useSsl', 'urlBase', 'updateLibrary', 'mapFrom', 'mapTo')]}])
        if path.endswith('/test'):
            if self.after_test:
                self.after_test()
            return httpx.Response(400 if self.fail_test else 200, json=[])
        if request.method == 'POST':
            self.rows[host].append({'id': 1, **json.loads(request.content)})
        rows = json.loads(json.dumps(self.rows[host]))
        if self.mask_tokens:
            for row in rows:
                for field in row['fields']:
                    if field['name'] == 'authToken':
                        field['value'] = '********'
        return httpx.Response(200, json=rows)


async def preview(store, upstream):
    checks = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.response)) as client:
        changes, notices = await build(store, client, checks=checks)
    return changes, notices, checks


async def test_review_is_read_only_redacted_and_limits_import_triggers(refresh_store):
    upstream = Upstream()
    changes, notices, checks = await preview(refresh_store, upstream)
    assert len(changes) == 3 and not notices
    assert all(method == 'GET' for method, _, _ in upstream.calls)
    public = json.dumps(public_plan({'revision': 2, 'changes': changes, 'notices': notices, 'checks': checks}))
    assert 'private-' not in public and 'authToken' not in public
    for change in changes[:2]:
        assert change['payload']['onDownload'] and change['payload']['onUpgrade']
        assert change['payload']['tags'] == [] and not change['payload']['onRename']
        assert not any(change['payload'].get(name) for name in ('onMovieDelete', 'onEpisodeFileDelete', 'onGrab'))
    assert changes[0]['payload']['onImportComplete'] is True
    assert changes[-1]['payload']['schedule'] == SCHEDULE


async def test_native_test_create_readback_and_repeat_preserve(refresh_store):
    upstream = Upstream()
    changes, _, _ = await preview(refresh_store, upstream)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.response)) as client:
        for change in changes:
            assert (await apply(refresh_store, client, change))['state'] == 'created'
        writes = [row for row in upstream.calls if row[0] == 'POST']
        assert [path for _, _, path in writes] == [
            '/api/v3/notification/test', '/api/v3/notification', '/api/v3/notification/test',
            '/api/v3/notification/test', '/api/v3/notification', '/api/v3/notification/test',
            '/api/v1/settings/jobs/' + JOB + '/schedule']
        for change in changes:
            assert (await apply(refresh_store, client, change))['state'] == 'preserved existing'
        assert [row for row in upstream.calls if row[0] == 'POST'] == writes
    assert (await preview(refresh_store, upstream))[0] == []


async def test_masked_saved_token_is_verified_using_saved_resource_id(refresh_store):
    upstream = Upstream()
    upstream.mask_tokens = True
    changes, _, _ = await preview(refresh_store, upstream)
    observed = []
    def record(request):
        if request.url.path.endswith('/test'):
            observed.append(json.loads(request.content))
        return upstream.response(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as client:
        assert (await apply(refresh_store, client, changes[0]))['state'] == 'created'
    assert 'id' not in observed[0]
    assert observed[1]['id'] == 1
    assert next(field['value'] for field in observed[1]['fields'] if field['name'] == 'authToken') == '********'


async def test_existing_plex_connections_and_custom_schedule_are_preserved(refresh_store):
    upstream = Upstream()
    upstream.rows = {key: [{'implementation': 'PlexServer', 'name': 'Existing custom connection'}] for key in upstream.rows}
    upstream.schedule = '0 */17 * * * *'
    changes, notices, checks = await preview(refresh_store, upstream)
    assert not changes and len(notices) == 3
    assert all(check['state'] == 'preserved' for check in checks)
    assert all(method == 'GET' for method, _, _ in upstream.calls)


async def test_authentication_failure_never_becomes_ready(refresh_store):
    upstream = Upstream()
    upstream.auth_error = True
    changes, notices, checks = await preview(refresh_store, upstream)
    assert not changes and notices and all(check['state'] == 'unavailable' for check in checks)


async def test_unclaimed_server_never_gets_connection_proposals(refresh_store):
    upstream = Upstream()
    upstream.claimed = False
    changes, notices, checks = await preview(refresh_store, upstream)
    assert not changes and 'claimed' in notices[0]
    assert all(check['state'] == 'unavailable' for check in checks)


async def test_disabled_libraries_prevent_schedule_change(refresh_store):
    upstream = Upstream()
    upstream.enabled = ['1']
    changes, notices, checks = await preview(refresh_store, upstream)
    assert len(changes) == 2 and notices
    assert next(check for check in checks if check['target'] == 'seerr')['state'] == 'unavailable'


async def test_unselected_unrelated_libraries_do_not_block_matching_import_libraries(refresh_store):
    upstream = Upstream()
    upstream.extra_libraries = [{'key': '99', 'type': 'movie', 'Location': [{'path': '/other-family-library'}]}]
    changes, _, _ = await preview(refresh_store, upstream)
    assert len(changes) == 3 and changes[-1]['kind'] == 'Plex availability schedule'


@pytest.mark.parametrize('change_upstream', ['machine', 'library_selection', 'schedule', 'config', 'test_failure'])
async def test_apply_rechecks_server_selection_schedule_and_settings(refresh_store, change_upstream):
    upstream = Upstream()
    changes, _, _ = await preview(refresh_store, upstream)
    target = changes[-1]
    if change_upstream == 'machine':
        upstream.machine = 'other-server'
    elif change_upstream == 'library_selection':
        upstream.enabled = ['1']
    elif change_upstream == 'schedule':
        upstream.schedule = '0 */17 * * * *'
    elif change_upstream == 'config':
        revision, config = refresh_store.config()
        refresh_store.save(config, revision)
    else:
        target = changes[0]
        upstream.fail_test = True
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.response)) as client:
        if change_upstream == 'schedule':
            assert (await apply(refresh_store, client, target))['state'] == 'preserved existing'
        else:
            with pytest.raises((Conflict, httpx.HTTPStatusError)):
                await apply(refresh_store, client, target)
    assert not any(method == 'POST' and path != '/api/v3/notification/test' for method, _, path in upstream.calls)


async def test_settings_edit_during_connection_test_blocks_creation(refresh_store):
    upstream = Upstream()
    changes, _, _ = await preview(refresh_store, upstream)
    def edit():
        revision, config = refresh_store.config()
        refresh_store.save(config, revision)
    upstream.after_test = edit
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.response)) as client:
        with pytest.raises(Conflict):
            await apply(refresh_store, client, changes[0])
    assert not upstream.rows['sonarr']


async def test_lost_create_response_is_not_retried_over_saved_connection(refresh_store):
    upstream = Upstream()
    changes, _, _ = await preview(refresh_store, upstream)
    def lost(request):
        result = upstream.response(request)
        if request.method == 'POST' and request.url.path == '/api/v3/notification':
            raise httpx.ReadError('Lost response')
        return result
    async with httpx.AsyncClient(transport=httpx.MockTransport(lost)) as client:
        with pytest.raises(httpx.ReadError):
            await apply(refresh_store, client, changes[0])
        assert (await apply(refresh_store, client, changes[0]))['state'] == 'preserved existing'
    assert len(upstream.rows['sonarr']) == 1
