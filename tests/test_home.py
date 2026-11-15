import json

import httpx
import pytest

from stackarr.home import artwork, progress


@pytest.fixture
def media(app):
    revision, config = app.state.store.config()
    for key in ('seerr', 'plex'):
        config.integrations[key].enabled = True
        config.integrations[key].url = f'http://{key}.test'
    config.integrations['plex'].browser_url = 'http://localhost:43600'
    app.state.store.save(config, revision, {key: {'api_key': 'PRIVATE-' + key} for key in ('seerr', 'plex')})
    calls = []
    details = {
        'id': 100, 'title': 'A movie', 'releaseDate': '2020-01-01', 'posterPath': '/abc.jpg',
        'mediaInfo': {'status': 1, 'requests': []},
    }

    def respond(request):
        calls.append(request)
        assert request.headers['X-Plex-Token' if request.url.host == 'plex.test' else 'X-Api-Key'].startswith('PRIVATE-')
        path = request.url.path
        if path.startswith('/imageproxy/'):
            return httpx.Response(200, content=b'\xff\xd8\xffjpegfixture', headers={'Content-Type': 'image/jpeg'})
        if path == '/identity':
            return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'expected-machine'}})
        if path.startswith('/library/metadata/'):
            return httpx.Response(200, json={'MediaContainer': {'Metadata': [{'ratingKey': '123', 'type': 'movie'}]}})
        if path == '/api/v1/settings/plex':
            return httpx.Response(200, json={'machineId': 'expected-machine', 'plexToken': 'DO-NOT-RETURN'})
        if request.method == 'POST':
            return httpx.Response(201, json={'id': 8, 'status': 2, 'requestedBy': {'plexToken': 'DO-NOT-RETURN'}})
        if path.startswith(('/api/v1/movie/', '/api/v1/tv/')):
            return httpx.Response(200, json=details)
        if path == '/api/v1/request':
            return httpx.Response(200, json={'pageInfo': {'pages': 2}, 'results': [
                {'id': 8, 'status': 2, 'requestedBy': {'email': 'DO-NOT-RETURN'},
                 'media': {'mediaType': 'movie', 'tmdbId': 100, 'status': 3}}]})
        if path == '/api/v1/media':
            return httpx.Response(200, json={'results': [{'mediaType': 'movie', 'tmdbId': 100, 'status': 5}]})
        return httpx.Response(200, json={'totalPages': 3, 'results': [details | {'mediaType': 'movie'},
            {'id': 12, 'mediaType': 'person', 'name': 'A person'}, details | {'id': 9, 'mediaType': 'movie', 'adult': True}]})
    app.state.home.transport = httpx.MockTransport(respond)
    return details, calls


def test_home_routes_require_owner_session(client):
    for path in ('/api/home', '/api/home/search?query=a', '/api/home/requests',
                 '/api/home/titles/movie/1', '/api/home/art/w342/a.jpg'):
        assert client.get(path).status_code == 401


@pytest.mark.asyncio
async def test_plex_link_uses_lan_route_without_changing_api_address(app, media):
    from stackarr.home import HomeError
    from stackarr.lan import browser_routes

    token = browser_routes.set({'plex': 'https://plex.home.arpa:29443'})
    try:
        url = await app.state.home.plex_link({'ratingKey': '123'}, 'movie')
        assert url.startswith('https://plex.home.arpa:29443/web/index.html#!/server/expected-machine/')
        assert app.state.store.config()[1].integrations['plex'].url == 'http://plex.test'
        browser_routes.set({})
        with pytest.raises(HomeError, match='home-network address'):
            await app.state.home.plex_link({'ratingKey': '123'}, 'movie')
    finally:
        browser_routes.reset(token)


def test_unconfigured_has_actionable_message_without_upstream(client, auth):
    response = client.get('/api/home')
    assert response.status_code == 409
    assert 'Connect Seerr in Apps' in response.json()['detail']


def test_search_normalizes_and_omits_people_adult_secrets_and_injected_urls(client, auth, media):
    details, calls = media
    details['posterPath'] = '//evil.test/secret.jpg'
    details['mediaInfo']['mediaUrl'] = 'javascript:evil'
    result = client.get('/api/home/search', params={'query': 'A & B', 'page': 2}).json()
    assert len(result['items']) == 1 and result['page'] == 2 and result['pages'] == 3
    assert result['items'][0]['poster'] == ''
    assert calls[0].url.params['query'] == 'A & B'
    assert 'query=A%20%26%20B' in str(calls[0].url)
    assert all(s not in json.dumps(result) for s in ('PRIVATE', 'javascript', 'evil.test'))


@pytest.mark.parametrize('url', ['/api/home/search?query=', '/api/home/search?query=a&page=0',
    '/api/home/search?query=a&page=501', '/api/home/titles/person/1', '/api/home/titles/movie/0',
    '/api/home/titles/movie/-1', '/api/home/requests?page=0'])
def test_invalid_input_never_reaches_upstream(client, auth, media, url):
    assert client.get(url).status_code == 422
    assert not media[1]


def test_home_independent_rows_and_request_paging(client, auth, media):
    home = client.get('/api/home').json()
    assert set(home) == {'available', 'requests', 'trending', 'movies', 'tv', 'checked_at'}
    assert home['available']['items'][0]['progress']['state'] == 'available'
    assert home['requests']['items'][0]['progress']['state'] == 'requested'
    assert 'DO-NOT-RETURN' not in json.dumps(home)
    client.get('/api/home/requests?page=2')
    assert next(r for r in reversed(media[1]) if r.url.path == '/api/v1/request').url.params['skip'] == '12'
    assert all(r.method == 'GET' for r in media[1])


def test_failed_row_does_not_hide_working_catalog(client, app, auth, media):
    original = app.state.home.transport
    def respond(request):
        if request.url.path == '/api/v1/media':
            return httpx.Response(500, json={'message': 'PRIVATE failure'})
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    result = client.get('/api/home').json()
    assert result['available']['error'] and result['trending']['items']
    assert 'PRIVATE' not in json.dumps(result)


def test_art_is_auth_bound_strict_and_bounded_cached(client, app, auth, media):
    for size, name in [('original', 'a.jpg'), ('w342', 'x.svg'), ('w342', '%2F%2Fevil.jpg')]:
        assert client.get('/api/home/art/' + size + '/' + name).status_code == 404
    for _ in range(2):
        result = client.get('/api/home/art/w342/abc.jpg')
        assert result.status_code == 200 and result.headers['Content-Type'] == 'image/jpeg'
    assert len(media[1]) == 1
    rev, config = app.state.store.config()
    app.state.store.save(config, rev)
    client.get('/api/home/art/w342/abc.jpg')
    assert len(media[1]) == 2


def test_post_requires_csrf_and_explicit_movie_request(client, auth, media):
    assert client.post('/api/home/titles/movie/100/request', json={}).status_code == 403
    assert not media[1]
    result = client.post('/api/home/titles/movie/100/request', json={}, headers=auth)
    assert result.status_code == 200 and result.json()['request_id'] == 8
    posts = [request for request in media[1] if request.method == 'POST']
    assert len(posts) == 1 and json.loads(posts[0].content) == {'mediaType': 'movie', 'mediaId': 100, 'is4k': False}
    assert 'DO-NOT-RETURN' not in result.text


def test_existing_movie_is_not_requested_twice(client, auth, media):
    media[0]['mediaInfo'] = {'status': 3, 'requests': [{'id': 5, 'status': 2}]}
    assert client.post('/api/home/titles/movie/100/request', json={}, headers=auth).status_code == 409
    assert all(request.method == 'GET' for request in media[1])


def test_seasons_keep_available_and_requested_episodes_out_of_new_request(client, auth, media):
    details, calls = media
    details.update(name='A show', seasons=[{'seasonNumber': n, 'name': 'Season ' + str(n)} for n in range(4)])
    details['mediaInfo'] = {'status': 4, 'seasons': [{'seasonNumber': 1, 'status': 5}],
                           'requests': [{'id': 2, 'status': 2, 'seasons': [{'seasonNumber': 2}]}]}
    result = client.get('/api/home/titles/tv/100').json()
    assert [(s['number'], s['requestable']) for s in result['seasons']] == [(1, False), (2, False), (3, True)]
    for seasons in ([], [0], [1], [2], [3, 3], [4]):
        assert client.post('/api/home/titles/tv/100/request', json={'seasons': seasons}, headers=auth).status_code == 409
    assert not any(r.method == 'POST' for r in calls)
    assert client.post('/api/home/titles/tv/100/request', json={'seasons': [3]}, headers=auth).status_code == 200
    assert json.loads(calls[-1].content)['seasons'] == [3]


def test_plex_link_live_machine_and_metadata_verified_and_token_free(client, auth, media):
    media[0]['mediaInfo'] = {'status': 5, 'ratingKey': '123', 'mediaUrl': 'https://evil.test/?token=PRIVATE'}
    result = client.get('/api/home/titles/movie/100').json()
    assert result['play_url'] == 'http://localhost:43600/web/index.html#!/server/expected-machine/details?key=%2Flibrary%2Fmetadata%2F123'
    assert all(s not in json.dumps(result) for s in ('PRIVATE', 'evil.test', 'DO-NOT-RETURN'))


@pytest.mark.parametrize('failure', ['wrong-machine', 'wrong-title', 'missing-item', 'authentication', 'redirect'])
def test_plex_failures_do_not_advertise_play(client, app, auth, media, failure):
    media[0]['mediaInfo'] = {'status': 5, 'ratingKey': '123'}
    original = app.state.home.transport
    def respond(request):
        if request.url.host == 'plex.test':
            if failure == 'authentication':
                return httpx.Response(401)
            if failure == 'redirect':
                return httpx.Response(302, headers={'Location': 'http://evil.test'})
            if failure == 'wrong-machine':
                return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'another-server'}})
            if failure == 'wrong-title' and request.url.path.startswith('/library/metadata/'):
                return httpx.Response(200, json={'MediaContainer': {'Metadata': [
                    {'ratingKey': '123', 'type': 'movie', 'Guid': [{'id': 'tmdb://999'}]}]}})
            if request.url.path.startswith('/library/metadata/'):
                return httpx.Response(200, json={'MediaContainer': {'Metadata': []}})
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    result = client.get('/api/home/titles/movie/100').json()
    assert result['play_url'] == '' and result['play_notice']
    assert 'evil.test' not in json.dumps(result)


def test_native_failed_request_is_still_saved_and_tracked(client, app, auth, media):
    original = app.state.home.transport
    def respond(request):
        if request.method == 'POST':
            return httpx.Response(201, json={'id': 8, 'status': 4})
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    result = client.post('/api/home/titles/movie/100/request', headers=auth, json={}).json()
    assert result['request_id'] == 8 and result['progress']['state'] == 'attention'


def test_native_jpg_mime_is_normalized_after_magic_validation(client, app, auth, media):
    app.state.home.transport = httpx.MockTransport(lambda r: httpx.Response(
        200, content=b'\xff\xd8\xffnative-jpeg', headers={'Content-Type': 'image/jpg'}))
    response = client.get('/api/home/art/w342/a.jpg')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'


def test_uncertain_submission_is_not_retried_or_leaked(client, app, auth, media):
    original = app.state.home.transport
    def respond(request):
        if request.method == 'POST':
            raise httpx.ReadTimeout('PRIVATE endpoint and credential')
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    result = client.post('/api/home/titles/movie/100/request', json={}, headers=auth)
    assert result.status_code == 409 and 'may have been saved' in result.text and 'PRIVATE' not in result.text


@pytest.mark.parametrize(('media', 'request_row', 'state'), [
    ({'status': 1}, None, 'discover'), ({'status': 2}, None, 'pending'),
    ({'status': 3}, None, 'requested'), ({'status': 4}, None, 'partial'),
    ({'status': 5}, None, 'available'), ({'status': 6}, None, 'blocked'),
    ({'status': 7}, None, 'deleted'), ({'status': 1}, {'status': 5}, 'checking'),
    ({'status': 3}, {'status': 4}, 'attention'),
    ({'status': 3, 'downloadStatus': [{'status': 'downloading'}]}, None, 'downloading'),
    ({'status': 3, 'downloadStatus': [{'status': 'completed'}]}, None, 'importing'),
    ({'status': 3, 'downloadStatus': [{'status': 'warning'}]}, None, 'attention'),
    ({'status': 1, 'status4k': 5}, {'status': 5, 'is4k': True}, 'available'),
])
def test_truthful_progress(media, request_row, state):
    assert progress(media, request_row)['state'] == state


def test_artwork_only_fixed_seerr_proxy_paths():
    assert artwork('/abc.jpg') == '/api/home/art/w342/abc.jpg'
    for bad in ('https://evil.test/x.jpg', '/../a.jpg', '/x.svg', '//a.jpg', '/a.jpg?token=secret'):
        assert artwork(bad) == ''


@pytest.fixture
def qualities(app, media):
    original = app.state.home.transport
    server = {'id': 0, 'name': 'Default', 'isDefault': True, 'is4k': False,
              'activeProfileId': 4, 'activeDirectory': '/data/media/movies'}
    profiles = [{'id': 9, 'name': 'Ultra-HD'}, {'id': 4, 'name': 'HD-1080p'}]
    def respond(request):
        if request.url.path.startswith('/api/v1/service/'):
            media[1].append(request)
            return httpx.Response(200, json={'server': server, 'profiles': profiles,
                'rootFolders': [{'path': '/data/media/movies'}]} if request.url.path.endswith('/0') else [server])
        if request.method == 'POST':
            media[1].append(request)
            body = json.loads(request.content)
            return httpx.Response(201, json={'id': 99, 'status': 2,
                'serverId': body.get('serverId'), 'profileId': body.get('profileId')})
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    return server, profiles


def test_real_quality_choices_keep_default_and_apply_only_to_the_explicit_request(client, auth, media, qualities):
    options = client.get('/api/home/titles/movie/100').json()['quality_options']
    assert options[0]['default'] and options[0]['profile'] == 'HD-1080p'
    assert all('rootFolder' not in row and 'apiKey' not in row for row in options)
    selected = next(row for row in options if row['profile'] == 'Ultra-HD')
    response = client.post('/api/home/titles/movie/100/request', headers=auth, json={'quality': selected['value']})
    assert response.json()['quality'] == 'Ultra-HD' and response.json()['quality_confirmed']
    post = next(row for row in media[1] if row.method == 'POST')
    assert json.loads(post.content) == {'mediaType': 'movie', 'mediaId': 100, 'is4k': False,
        'serverId': 0, 'profileId': 9, 'rootFolder': '/data/media/movies'}
    assert all(row.method == 'GET' or row.url.path == '/api/v1/request' for row in media[1])


@pytest.mark.parametrize('change', ['default', 'profile', 'folder', 'expired', 'title', 'config'])
def test_stale_or_reused_quality_never_submits_with_a_fallback(client, app, auth, media, qualities, change):
    option = client.get('/api/home/titles/movie/100').json()['quality_options'][0]['value']
    server, profiles = qualities
    if change == 'default':
        server['isDefault'] = False
    if change == 'profile':
        profiles[0]['name'] = 'Changed'
    if change == 'folder':
        server['activeDirectory'] = '/changed'
    if change == 'expired':
        app.state.home.quality_choices[option]['expires'] = 0
    if change == 'config':
        revision, config = app.state.store.config()
        app.state.store.save(config, revision)
    result = client.post('/api/home/titles/movie/' + ('101' if change == 'title' else '100') + '/request',
                         headers=auth, json={'quality': option})
    assert result.status_code == 409
    assert not any(row.method == 'POST' for row in media[1])


def test_existing_show_cannot_promise_a_different_quality_for_additional_seasons(client, auth, media, qualities):
    media[0].update(seasons=[{'seasonNumber': 2}], mediaInfo={'status': 4, 'requests': [{'id': 5, 'status': 2}]})
    detail = client.get('/api/home/titles/tv/100').json()
    assert detail['existing_series'] and not detail['quality_options'] and 'existing' in detail['quality_notice']
    result = client.post('/api/home/titles/tv/100/request', headers=auth, json={'seasons': [2], 'quality': 'forged'})
    assert result.status_code == 409 and not any(row.method == 'POST' for row in media[1])


@pytest.mark.parametrize('bad', [[], [{'id': 1, 'name': 'a'}, {'id': 1, 'name': 'b'}], [{'id': [], 'name': 'broken'}]])
def test_missing_or_malformed_profiles_leave_a_recoverable_title(client, auth, media, qualities, bad):
    qualities[1][:] = bad
    detail = client.get('/api/home/titles/movie/100')
    assert detail.status_code == 200 and not detail.json()['quality_options'] and detail.json()['quality_notice']


@pytest.mark.parametrize('kind', ['movie', 'tv'])
def test_imported_files_wait_for_plex_without_becoming_playable(client, app, auth, media, kind):
    revision, config = app.state.store.config()
    arr = 'radarr' if kind == 'movie' else 'sonarr'
    config.integrations[arr].enabled = True
    config.integrations[arr].url = 'http://' + arr + '.test'
    app.state.store.save(config, revision, {arr: {'api_key': 'PRIVATE-arr'}})
    media[0]['mediaInfo'] = {'status': 3, 'tmdbId': 100, 'tvdbId': 555, 'externalServiceId': 10, 'serviceId': 0,
        'requests': [{'id': 5, 'status': 2, 'seasons': [{'seasonNumber': 1}]}]}
    original = app.state.home.transport
    def respond(request):
        if request.url.path == '/api/v1/settings/' + arr:
            return httpx.Response(200, json=[{'id': 0, 'hostname': arr + '.test', 'port': 80, 'is4k': False, 'apiKey': 'PRIVATE-arr'}])
        if request.url.host == arr + '.test':
            return httpx.Response(200, json={'tmdbId': 100, 'tvdbId': 555, 'hasFile': True, 'movieFile': {'id': 1},
                'seasons': [{'seasonNumber': 1, 'statistics': {'episodeCount': 6, 'episodeFileCount': 6}}]})
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    detail = client.get(f'/api/home/titles/{kind}/100').json()
    assert detail['progress']['state'] == 'imported' and detail['play_url'] == ''
    assert 'PRIVATE-arr' not in json.dumps(detail)


def test_failed_or_wrong_arr_cannot_hide_requests_or_invent_an_import(client, app, auth, media):
    revision, config = app.state.store.config()
    config.integrations["radarr"].enabled = True
    config.integrations["radarr"].url = 'http://radarr.test'
    app.state.store.save(config, revision, {'radarr': {'api_key': 'PRIVATE-arr'}})
    media[0]['mediaInfo'] = {'status': 3, 'tmdbId': 100, 'externalServiceId': 10, 'serviceId': 0}
    original = app.state.home.transport
    def respond(request):
        if request.url.path == '/api/v1/settings/radarr':
            return httpx.Response(200, json=[{'id': 0, 'hostname': 'other.test', 'port': 80, 'is4k': False, 'apiKey': 'PRIVATE-arr'}])
        assert request.url.host != 'radarr.test'
        return original.handler(request)
    app.state.home.transport = httpx.MockTransport(respond)
    detail = client.get('/api/home/titles/movie/100').json()
    assert detail['progress']['state'] == 'requested' and not detail['play_url']




def test_saved_requested_quality_survives_reopening_and_does_not_leak_service_fields(client, auth, media, qualities):
    media[0]['mediaInfo'] = {'status': 3, 'requests': [{'id': 5, 'status': 2, 'serverId': 0, 'profileId': 9}]}
    detail = client.get('/api/home/titles/movie/100').json()
    assert detail['requested_quality'] == '4K / UHD'
    assert 'PRIVATE' not in json.dumps(detail)
