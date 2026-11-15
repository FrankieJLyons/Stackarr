import copy
import json

import httpx
import pytest

from stackarr.home import Home, HomeError, TitleRequest
from stackarr.quality_rules import ALLOWED, Policy, QualityRules, ReviewIntent, curated, decide
from stackarr.store import Conflict, Store


def schema():
    names = ['Unknown', 'CAM', 'WORKPRINT', 'DVDSCR', 'DVD', 'SDTV', 'WEBDL-480p',
             'WEBDL-1080p', 'Bluray-1080p', 'Remux-1080p', 'WEBDL-2160p', 'Bluray-2160p',
             'HDTV-720p', 'WEBRip-720p', 'WEBDL-720p', 'Bluray-720p']
    items = [{'quality': {'id': i + 50, 'name': name, 'modifier': 'none'}, 'items': [], 'allowed': False}
             for i, name in enumerate(names)]
    items[5:7] = [{'id': 1007, 'name': 'SD group', 'allowed': False, 'items': items[5:7]}]
    return {'name': '', 'upgradeAllowed': False, 'cutoff': 0, 'items': items,
            'minFormatScore': 0, 'cutoffFormatScore': 0, 'minUpgradeFormatScore': 0, 'formatItems': []}


class Arr:
    def __init__(self, store, app):
        self.store, self.app = store, app
        self.profiles = [{**curated(schema(), '1080p')[0], 'id': 7, 'name': 'Original'}]
        key = 'tvdbId' if app == 'sonarr' else 'tmdbId'
        self.titles = [{'id': i, key: i + 100, 'title': f'Title {i}', 'year': year, 'qualityProfileId': 7,
                        'monitored': False, 'path': '/untouched', 'tags': [15]} for i, year in enumerate([1999, 2000, 2010, 0], 1)]
        self.writes = []
        self.after_read = None
        self.fail_write = False
        self.formats = []
        self.fail_format_write = False

    def respond(self, request):
        assert request.url.host == self.app + '.test'
        path = request.url.path
        if request.method == 'GET':
            if path.endswith('customformat/schema'):
                data = [{'implementation': 'ReleaseTitleSpecification', 'fields': [{'name': 'value'}]}]
            elif path.endswith('/customformat'):
                data = self.formats
            elif path.endswith('qualityprofile/schema'):
                data = schema()
                data['formatItems'] = [{'format': row['id'], 'name': row['name'], 'score': 0} for row in self.formats]
            elif path.endswith('/qualityprofile'):
                data = self.profiles
            elif '/qualityprofile/' in path:
                data = next(row for row in self.profiles if row['id'] == int(path.split('/')[-1]))
            elif path.split('/')[-1].isdigit():
                data = next(row for row in self.titles if row['id'] == int(path.split('/')[-1]))
            else:
                data = self.titles
            if self.after_read:
                self.after_read(request)
            return httpx.Response(200, json=copy.deepcopy(data))
        body = json.loads(request.content)
        self.writes.append((request.method, path, body))
        if path.endswith('/customformat'):
            created = {**body, 'id': 700 + len(self.formats)}
            self.formats.append(created)
            for profile in self.profiles:
                profile['formatItems'].append({'format': created['id'], 'name': created['name'], 'score': 0})
            if self.fail_format_write:
                self.fail_format_write = False
                raise httpx.ReadError('Lost response after custom format creation')
            return httpx.Response(201, json=created)
        if path.endswith('/qualityprofile'):
            created = {**body, 'id': 100 + len(self.profiles)}
            self.profiles.append(created)
            if self.fail_write:
                self.fail_write = False
                raise httpx.ReadError('Lost response after profile creation')
            return httpx.Response(201, json=created)
        assert request.method == 'PUT' and path.endswith('/editor')
        key = 'seriesIds' if self.app == 'sonarr' else 'movieIds'
        assert set(body) == {key, 'qualityProfileId', 'moveFiles'} and body['moveFiles'] is False
        with self.store.db() as db:
            assert db.execute('SELECT COUNT(*) FROM quality_runs').fetchone()[0] > 0
        for row in self.titles:
            if row['id'] in body[key]:
                row['qualityProfileId'] = body['qualityProfileId']
        if self.fail_write:
            self.fail_write = False
            raise httpx.ReadError('Lost response after assignment')
        return httpx.Response(200, json=self.titles)


@pytest.fixture(params=['sonarr', 'radarr'])
def fixture(tmp_path, request):
    store = Store(tmp_path)
    revision, config = store.config()
    app = request.param
    config.integrations[app].enabled = True
    config.integrations[app].url = f'http://{app}.test'
    store.save(config, revision, {app: {'api_key': 'PRIVATE-test-key'}})
    arr = Arr(store, app)
    home = Home(store, httpx.MockTransport(arr.respond))
    return store, app, arr, home


async def save_rules(fixture, policy=None):
    _, app, _, home = fixture
    policy = policy or Policy(exceptions=[{'media_id': 103, 'title': 'Title 3', 'tier': '4K'}])
    review = await home.rules.review(ReviewIntent(app=app, revision=home.rules.saved(app)[0], policy=policy))
    await home.rules.apply(review)
    return policy


@pytest.mark.parametrize('year,media,tier', [(1999, 10, 'SD'), (2000, 10, '1080p'), (2020, 10, '1080p'),
    (None, 10, None), (0, 10, None), (True, 10, None), ('1990', 10, None), (1990, 11, '4K'), (None, 11, '4K')])
def test_rule_precedence_and_exact_boundary(year, media, tier):
    policy = Policy(exceptions=[{'media_id': 11, 'title': 'A title', 'tier': '4K'}])
    assert decide(policy, media, year)[0] == tier


async def test_save_creates_curated_profiles_without_assignments_and_is_idempotent(fixture):
    store, app, arr, home = fixture
    original = copy.deepcopy(arr.profiles[0])
    policy = await save_rules(fixture)
    assert len(arr.writes) == 3 and all(row[0] == 'POST' for row in arr.writes)
    assert arr.profiles[0] == original and {row['qualityProfileId'] for row in arr.titles} == {7}
    for tier, saved in home.rules.saved(app)[3].items():
        payload, names = curated(schema(), tier)
        assert set(names) <= ALLOWED[tier] and not payload['upgradeAllowed']
        assert not set(names) & {'CAM', 'WORKPRINT', 'DVDSCR', 'Remux-1080p'}
        assert saved['id'] >= 100
    await save_rules(fixture, policy)
    assert len(arr.writes) == 3
    assert 'PRIVATE-test-key' not in json.dumps(home.rules.read(app))
    assert b'PRIVATE-test-key' not in store.path.read_bytes()
    assert home.rules.read(app)['policy']['exceptions'] == policy.model_dump()['exceptions']


async def test_library_preview_apply_restart_and_undo_preserve_files_and_other_fields(fixture):
    store, app, arr, home = fixture
    policy = await save_rules(fixture)
    original = copy.deepcopy(arr.titles)
    plan = await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy, scope='library'))
    public = home.rules.public(plan)
    assert public['change_count'] == 3
    assert [row['tier'] for row in public['changes']] == ['SD', '1080p', '4K', None]
    assert [row['qualityProfileId'] for row in arr.titles] == [7] * 4
    result = await home.rules.apply(plan)
    assert {row['state'] for row in result['rows']} == {'applied'}
    assert arr.titles[3] == original[3]
    for before, after in zip(original, arr.titles):
        assert {k: v for k, v in before.items() if k != 'qualityProfileId'} == {k: v for k, v in after.items() if k != 'qualityProfileId'}
    restarted = QualityRules(Store(store.root), home.call)
    assert restarted.read(app)['history'][0]['id'] == result['id']
    undone = await restarted.undo(app, result['id'])
    assert {row['state'] for row in undone['rows']} == {'undone'} and arr.titles == original


async def test_lost_profile_response_can_resume_without_duplicate_profiles(fixture):
    _, _, arr, _ = fixture
    arr.fail_write = True
    with pytest.raises(HomeError):
        await save_rules(fixture)
    await save_rules(fixture)
    assert len(arr.profiles) == 4 and len(arr.writes) == 3


async def test_lost_assignment_response_and_later_user_change_are_not_blindly_overwritten(fixture):
    _, app, arr, home = fixture
    policy = await save_rules(fixture)
    plan = await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy, scope='library'))
    arr.fail_write = True
    result = await home.rules.apply(plan)
    assert result['rows'][0]['state'] == 'uncertain' and result['rows'][1]['state'] == 'pending'
    # A later manual title edit must win, including after a lost response.
    arr.titles[0]['qualityProfileId'] = 999
    undone = await home.rules.undo(app, result['id'])
    assert undone['rows'][0]['state'] == 'undo-conflict' and arr.titles[0]['qualityProfileId'] == 999


@pytest.mark.parametrize('change', ['profile', 'title', 'config', 'rules'])
async def test_stale_reviews_have_no_writes(fixture, change):
    store, app, arr, home = fixture
    policy = await save_rules(fixture)
    plan = await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy, scope='library'))
    arr.writes.clear()
    if change == 'profile':
        arr.profiles[0]['name'] = 'Changed'
    elif change == 'title':
        arr.titles[0]['year'] = 2001
    elif change == 'config':
        revision, config = store.config()
        store.save(config, revision)
    else:
        with store.db() as db:
            db.execute('UPDATE quality_rules SET revision=revision+1')
    with pytest.raises((ValueError, Conflict)):
        await home.rules.apply(plan)
    assert not arr.writes


async def test_native_read_only_review_never_authorizes_any_write(fixture):
    store, app, arr, home = fixture
    revision, config = store.config()
    config.integrations[app].read_only = True
    store.save(config, revision)
    plan = await home.rules.review(ReviewIntent(app=app, revision=0, policy=Policy()))
    assert home.rules.public(plan)['read_only']
    with pytest.raises(ValueError, match='read-only'):
        await home.rules.apply(plan)
    assert not arr.writes


async def test_new_feature_startup_and_reads_preserve_update_fingerprint(fixture):
    from stackarr.controller_connections import connected_apps, progress, refresh_ports
    from stackarr.self_update import fingerprint

    store, app, arr, home = fixture
    identity = 'a' * 32
    with store.db() as db:
        db.execute('CREATE TABLE controller_connections (id TEXT PRIMARY KEY, revision INTEGER, ports TEXT, activated INTEGER)')
        db.execute('INSERT INTO controller_connections VALUES(?,?,?,0)', (identity, 1, json.dumps({'sonarr': 18990})))
    before = fingerprint(store.root)
    restarted = Home(Store(store.root), home.transport)
    assert restarted.rules.read(app)['revision'] == 0
    await restarted.rules.review(ReviewIntent(app=app, revision=0, policy=Policy()))
    assert not connected_apps(store, identity)
    assert progress(store, identity)[0]['state'] == 'pending'
    refresh_ports(store, [])
    assert fingerprint(store.root) == before and not arr.writes


async def test_connection_race_before_editor_write_is_blocked(fixture):
    store, app, arr, home = fixture
    policy = await save_rules(fixture)
    plan = await home.rules.review(ReviewIntent(app=app, revision=1, policy=policy, scope='library'))
    reads = 0
    def race(request):
        nonlocal reads
        if request.url.path.endswith('/qualityprofile'):
            reads += 1
            if reads == 2:  # Review passes, then connection changes during the final pre-write read.
                revision, config = store.config()
                config.integrations[app].url = 'http://different.test'
                store.save(config, revision)
    arr.after_read = race
    arr.writes.clear()
    result = await home.rules.apply(plan)
    assert not arr.writes and result['rows'][0]['state'] == 'uncertain'


@pytest.mark.parametrize('format_preferences', [False, True])
@pytest.mark.parametrize('stale_seerr_profiles', [False, True])
async def test_future_request_uses_exception_and_refuses_changed_profile_or_server(
        fixture, format_preferences, stale_seerr_profiles):
    store, app, arr, home = fixture
    await save_rules(fixture, Policy(exceptions=[{'media_id': 103, 'title': 'Title 3', 'tier': '4K'}],
                                    formats={'block_dolby_vision': format_preferences}))
    revision, config = store.config()
    config.integrations['seerr'].enabled = True
    config.integrations['seerr'].url = 'http://seerr.test'
    store.save(config, revision, {'seerr': {'api_key': 'PRIVATE-seerr-key'}})
    kind = 'tv' if app == 'sonarr' else 'movie'
    identity = 555 if kind == 'tv' else 103
    server = {'id': 0, 'isDefault': True, 'is4k': False, 'activeProfileId': 7, 'activeDirectory': '/media'}
    settings = {'id': 0, 'hostname': app + '.test', 'port': 80, 'apiKey': 'PRIVATE-test-key'}
    details = {'id': identity, 'title': 'Title 3', 'firstAirDate': '1990-01-01', 'releaseDate': '1990-01-01',
               'externalIds': {'tvdbId': 103}, 'seasons': [{'seasonNumber': 1}], 'mediaInfo': {'status': 1}}
    posted = []
    seerr_profiles = copy.deepcopy(arr.profiles[:1] if stale_seerr_profiles else arr.profiles)
    def respond(request):
        if request.url.host == app + '.test':
            return arr.respond(request)
        if request.method == 'POST':
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={'id': 50, 'status': 2, **posted[-1]})
        path = request.url.path
        if path.startswith('/api/v1/service/'):
            return httpx.Response(200, json={'server': server, 'profiles': seerr_profiles,
                'rootFolders': [{'path': '/media'}]} if path.endswith('/0') else [server])
        if path.startswith('/api/v1/settings/'):
            return httpx.Response(200, json=[settings])
        return httpx.Response(200, json=details)
    home.transport = httpx.MockTransport(respond)
    options = await home.quality_options(kind, identity)
    assert options[0]['default'] and options[0]['profile'] == home.rules.saved(app)[3]['4K']['payload']['name']
    assert options[0]['label'] == '4K'
    chosen, _ = await home.selected_quality(kind, identity, options[0]['value'])
    assert chosen['profileId'] == home.rules.saved(app)[3]['4K']['id']
    # Send the request while Seerr still has its old list.
    await home.request(kind, identity, TitleRequest(
        seasons=[1] if kind == 'tv' else [], quality=options[0]['value'] if stale_seerr_profiles else ''))
    assert posted[0]['profileId'] == home.rules.saved(app)[3]['4K']['id']
    assert len(posted) == 1
    # A later cache refresh must not invalidate the reviewed choice. Live profile,
    # custom-format and server edits must still be refused below.
    seerr_profiles[:] = copy.deepcopy(list(reversed(arr.profiles)))
    assert (await home.selected_quality(kind, identity, options[0]['value']))[0] == chosen
    if format_preferences:
        original_pattern = arr.formats[0]['specifications'][0]['fields'][0]['value']
        arr.formats[0]['specifications'][0]['fields'][0]['value'] = 'NEVER_MATCH'
        with pytest.raises(HomeError, match='filter changed'):
            await home.request(kind, identity, TitleRequest(seasons=[1] if kind == 'tv' else []))
        arr.formats[0]['specifications'][0]['fields'][0]['value'] = original_pattern
        assert len(posted) == 1
    settings['hostname'] = 'foreign.test'
    with pytest.raises(HomeError, match='different app'):
        await home.request(kind, identity, TitleRequest(seasons=[1] if kind == 'tv' else []))
    settings['hostname'] = app + '.test'
    arr.profiles[-1]['upgradeAllowed'] = True
    with pytest.raises(HomeError, match='profile changed'):
        await home.selected_quality(kind, identity, options[0]['value'])
    assert len(posted) == 1


def test_quality_routes_require_auth_csrf_review_and_one_use_token(client, app, auth):
    store = app.state.store
    revision, config = store.config()
    config.integrations['radarr'].enabled = True
    config.integrations['radarr'].url = 'http://radarr.test'
    store.save(config, revision, {'radarr': {'api_key': 'PRIVATE-test-key'}})
    arr = Arr(store, 'radarr')
    app.state.home.transport = httpx.MockTransport(arr.respond)
    intent = {'app': 'radarr', 'revision': 0, 'policy': Policy().model_dump()}
    assert client.post('/api/quality-rules/review', json=intent).status_code == 403
    review = client.post('/api/quality-rules/review', headers=auth, json=intent)
    assert review.status_code == 200 and 'PRIVATE' not in review.text and 'api_key' not in review.text
    token = {'review_token': review.json()['review_token']}
    assert client.post('/api/quality-rules/apply', headers=auth, json=token).status_code == 200
    assert client.post('/api/quality-rules/apply', headers=auth, json=token).status_code == 409
    client.post('/api/logout', headers=auth)
    assert client.get('/api/quality-rules/radarr').status_code == 401
    assert client.get('/api/quality-rules/radarr/titles').status_code == 401


@pytest.mark.parametrize('preset_index', [0, 1, 2])
async def test_preset_creates_only_selected_resolution_without_touching_library(fixture, preset_index):
    from stackarr.quality_presets import catalog
    _, app, arr, home = fixture
    original = copy.deepcopy((arr.profiles, arr.titles))
    recipe = catalog()['presets'][preset_index]
    policy = Policy.model_validate(recipe['policy'])
    plan = await home.rules.review(ReviewIntent(app=app, revision=0, policy=policy))
    assert list(plan['plans']) == [recipe['tier']]
    assert not arr.writes
    await home.rules.apply(plan)
    assert len(arr.writes) == 1 and arr.writes[0][:2] == ('POST', '/api/v3/qualityprofile')
    assert arr.profiles[:-1] == original[0] and arr.titles == original[1]
    assert not arr.profiles[-1]['upgradeAllowed']
    assert set(plan['plans'][recipe['tier']]['qualities']) <= ALLOWED[recipe['tier']]
    assert decide(policy, 333, None)[0] == recipe['tier']
    assert not policy.formats.block_dolby_vision
    assert not any(row['score'] for row in arr.profiles[-1]['formatItems'])


async def test_previous_policy_survives_restart_and_restores_without_deleting_profiles(fixture):
    from stackarr.quality_presets import catalog
    store, app, arr, home = fixture
    original = await save_rules(fixture)
    await save_rules(fixture, Policy.model_validate(catalog()['presets'][0]['policy']))
    assert home.rules.read(app)['can_restore_rules']
    restored = QualityRules(Store(store.root), home.rules.call)
    plan = await restored.review(restored.restore_intent(app))
    assert Policy.model_validate(plan['policy']) == original
    before = copy.deepcopy((arr.profiles, arr.titles, arr.writes))
    await restored.apply(plan)
    assert restored.saved(app)[1] == original
    assert (arr.profiles, arr.titles, arr.writes) == before


async def test_first_preset_can_restore_paused_rules_and_stale_restore_is_rejected(fixture):
    from stackarr.quality_presets import catalog
    store, app, arr, home = fixture
    await save_rules(fixture, Policy.model_validate(catalog()['presets'][0]['policy']))
    plan = await home.rules.review(home.rules.restore_intent(app))
    assert not plan['policy']['enabled']
    await save_rules(fixture, Policy(older='4K', newer='4K', selected_profiles=True))
    with pytest.raises(Conflict):
        await home.rules.apply(plan)
    revision, config = store.config()
    config.integrations[app].url = 'http://replacement.test'
    store.save(config, revision, {})
    assert not home.rules.read(app)['can_restore_rules']
    with pytest.raises(Conflict):
        home.rules.restore_intent(app)
    with store.db() as db:
        encrypted = db.execute('SELECT value FROM quality_rule_restore').fetchone()[0]
    assert b'PRIVATE' not in encrypted and b'api_key' not in encrypted


async def test_uniform_720p_request_resolves_one_live_profile_without_a_release_year(fixture):
    from stackarr.quality_presets import catalog
    store, app, arr, home = fixture
    await save_rules(fixture, Policy.model_validate(catalog()['presets'][1]['policy']))
    revision, config = store.config()
    config.integrations['seerr'].enabled = True
    config.integrations['seerr'].url = 'http://seerr.test'
    store.save(config, revision, {'seerr': {'api_key': 'synthetic'}})

    def respond(request):
        if request.url.host == app + '.test':
            return arr.respond(request)
        assert request.url.host == 'seerr.test' and request.method == 'GET'
        assert request.url.path == '/api/v1/settings/' + app
        return httpx.Response(200, json=[{'id': 0, 'hostname': app + '.test', 'port': 80, 'apiKey': 'PRIVATE-test-key'}])

    home.transport = httpx.MockTransport(respond)
    kind = 'tv' if app == 'sonarr' else 'movie'
    choice = await home.rules.request_choice(kind, {'id': 123, 'externalIds': {'tvdbId': 123}}, {'id': 0})
    assert choice['tier'] == '720p' and choice['profile_id'] == home.rules.saved(app)[3]['720p']['id']
    assert len(choice['verified_profiles']) == 1


def test_preset_catalog_and_restore_use_session_csrf_and_single_use_review(client, app, auth):
    store = app.state.store
    revision, config = store.config()
    config.integrations['sonarr'].enabled = True
    config.integrations['sonarr'].url = 'http://sonarr.test'
    store.save(config, revision, {'sonarr': {'api_key': 'PRIVATE-test-key'}})
    arr = Arr(store, 'sonarr')
    app.state.home.transport = httpx.MockTransport(arr.respond)
    recipes = client.get('/api/quality-presets').json()
    assert [row['tier'] for row in recipes['presets']] == ['1080p', '720p', '4K']
    intent = {'app': 'sonarr', 'revision': 0, 'policy': recipes['presets'][0]['policy']}
    review = client.post('/api/quality-rules/review', headers=auth, json=intent).json()
    assert client.post('/api/quality-rules/apply', headers=auth, json={'review_token': review['review_token']}).status_code == 200
    assert client.post('/api/quality-rules/sonarr/restore-review', json={}).status_code == 403
    restore = client.post('/api/quality-rules/sonarr/restore-review', headers=auth, json={})
    assert restore.status_code == 200 and not restore.json()['policy']['enabled']
    assert 'PRIVATE' not in restore.text and 'api_key' not in restore.text
    token = {'review_token': restore.json()['review_token']}
    assert client.post('/api/quality-rules/apply', headers=auth, json=token).status_code == 200
    assert client.post('/api/quality-rules/apply', headers=auth, json=token).status_code == 409
    client.post('/api/logout', headers=auth)
    assert client.get('/api/quality-presets').status_code == 401
    assert client.post('/api/quality-rules/sonarr/restore-review', headers=auth, json={}).status_code == 401
