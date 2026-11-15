"""Network-disabled smoke for the exact packaged dashboard image."""
import json
import tempfile

import httpx
from fastapi.testclient import TestClient

from stackarr.server import create_app


def respond(request):
    path = request.url.path
    if path == '/identity':
        return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'fixture'}})
    if path.startswith('/library/metadata/'):
        return httpx.Response(200, json={'MediaContainer': {'Metadata': [{'ratingKey': '123', 'type': 'movie', 'Guid': [{'id': 'tmdb://200'}]}]}})
    if path.startswith('/api/v1/service/radarr'):
        server={'id':0,'name':'Image fixture','isDefault':True,'is4k':False,'activeDirectory':'/data/media/movies','activeProfileId':9}
        return httpx.Response(200,json={'server':server,'profiles':[{'id':9,'name':'Ultra-HD'}],'rootFolders':[{'path':'/data/media/movies'}]} if path.endswith('/0') else [server])
    if path == '/api/v1/settings/plex':
        return httpx.Response(200, json={'machineId': 'fixture'})
    if request.method == 'POST':
        assert json.loads(request.content) == {'mediaType': 'movie', 'mediaId': 100, 'is4k': False,'serverId':0,'profileId':9,'rootFolder':'/data/media/movies'}
        return httpx.Response(201, json={'id': 1, 'status': 2,'serverId':0,'profileId':9})
    item = {'id': 200 if path.endswith('/200') else 100, 'title': 'Packaged fixture',
            'mediaType': 'movie', 'mediaInfo': {'status': 5, 'ratingKey': '123', 'tmdbId': 200} if path.endswith('/200') else {}}
    if '/movie/' in path:
        return httpx.Response(200, json=item)
    if path == '/api/v1/search':
        assert request.url.params['query'] == 'Two words'
        assert 'Two%20words' in str(request.url)
    return httpx.Response(200, json={'results': [] if path in ('/api/v1/request', '/api/v1/media') else [item]})


with tempfile.TemporaryDirectory() as directory:
    app = create_app(directory, origin='http://testserver', transport=httpx.MockTransport(respond), background=False)
    rev, config = app.state.store.config()
    for key in ('seerr', 'plex'):
        config.integrations[key].enabled = True
        config.integrations[key].url = 'http://' + key + '.fixture'
        config.integrations[key].browser_url = 'http://localhost:43600'
    app.state.store.save(config, rev, {key: {'api_key': 'fixture'} for key in ('seerr', 'plex')})
    with TestClient(app) as client:
        assert client.get('/api/home').status_code == 401
        for asset in ('home.js', 'home.css', 'app.js'):
            assert client.get('/static/' + asset).status_code == 200
        headers = {'Origin': 'http://testserver'}
        client.post('/api/setup', headers=headers, json={'password': 'packaged fixture password',
                    'setup_token': (app.state.store.root / 'setup-token').read_text()}).raise_for_status()
        result = client.post('/api/login', headers=headers, json={'password': 'packaged fixture password'})
        headers['X-CSRF-Token'] = result.json()['csrf']
        assert client.get('/api/home').json()['trending']['items']
        assert client.get('/api/home/search?query=Two%20words').json()['items']
        assert client.post('/api/home/titles/movie/100/request', json={}).status_code == 403
        quality=client.get('/api/home/titles/movie/100').json()['quality_options'][0]['value']
        saved=client.post('/api/home/titles/movie/100/request', json={'quality':quality}, headers=headers).json()
        assert saved['progress']['state'] == 'requested' and saved['quality']=='Ultra-HD' and saved['quality_confirmed']
        assert client.get('/api/home/titles/movie/200').json()['play_url'].endswith('key=%2Flibrary%2Fmetadata%2F123')
        assert 'target="_blank"' not in client.get('/static/home.js').text
print(json.dumps({'passed': True, 'exact_image_assets_and_api': True, 'network_disabled': True,
                  'owner_csrf_request_and_verified_plex_link': True, 'fixtures_only': True}))
