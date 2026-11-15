"""Loopback-only design preview. Catalog/art captured from disposable Seerr.

All request/progress/Plex responses here are fixtures; no media app is contacted.
The real authenticated Stackarr API and frontend run against the fixture transport.
"""
import copy
import json
from pathlib import Path

import httpx
import uvicorn
from fastapi.responses import HTMLResponse

from stackarr.server import create_app, password_hash

ROOT = Path('test-results/home-screen-20261020').resolve()
ORIGIN = 'http://127.0.0.2:29330'
PASSWORD = 'Stackarr home preview'


class Catalog:
    def __init__(self):
        self.titles = json.loads((ROOT / 'catalog.json').read_text())
        self.media, self.requests = {}, []
        for index, (key, item) in enumerate(self.titles.items()):
            status = (5, 3, 1, 3, 4, 1, 2, 3)[index]
            media = {'id': index + 1, 'tmdbId': item['id'], 'mediaType': item['mediaType'],
                'status': status, 'ratingKey': '123' if index == 0 else '456' if index == 4 else None,
                'requests': [], 'seasons': [{'seasonNumber': 1, 'status': 5}] if index == 4 else []}
            if index in (1, 3):
                media['downloadStatus'] = [{'status': 'downloading' if index == 1 else 'completed'}]
            if status in (2, 3):
                request = {'id': index + 1, 'status': 4 if index == 7 else 1 if index == 6 else 2,
                    'is4k': False, 'seasons': [{'seasonNumber': 1}] if item['mediaType'] == 'tv' else []}
                self.requests.append(request | {'media': media})
                media['requests'] = [request]
            self.media[key] = media

    def handle(self, request):
        path = request.url.path
        if path.startswith('/imageproxy/'):
            size, name = path.split('/')[-2:]
            art = ROOT / 'art' / (size + '-' + name)
            if art.is_file():
                return httpx.Response(200, content=art.read_bytes(), headers={'Content-Type': 'image/png' if name.endswith('.png') else 'image/jpeg'})
            return httpx.Response(404)
        if path == '/identity':
            return httpx.Response(200, json={'MediaContainer': {'machineIdentifier': 'home-preview-simulated'}})
        if path.startswith('/library/metadata/'):
            key = path.rsplit('/', 1)[-1]
            return httpx.Response(200, json={'MediaContainer': {'Metadata': [{'ratingKey': key, 'type': 'movie' if key == '123' else 'show'}]}})
        if path.startswith('/api/v1/service/'):
            server={'id':0,'name':'Preview request service','is4k':False,'isDefault':True,'activeProfileId':1,'activeDirectory':'/preview-only'}
            return httpx.Response(200,json={'server':server,'profiles':[{'id':1,'name':'HD-1080p'},{'id':2,'name':'Ultra-HD'},{'id':3,'name':'HD-720p'}],'rootFolders':[{'path':'/preview-only'}]} if path.endswith('/0') else [server])
        if path == '/api/v1/settings/plex':
            return httpx.Response(200, json={'machineId': 'home-preview-simulated'})
        if request.method == 'POST' and path == '/api/v1/request':
            intent = json.loads(request.content)
            key = f'{intent["mediaType"]}-{intent["mediaId"]}'
            media = self.media[key]
            media['status'] = 3
            saved = {'serverId':intent.get('serverId'),'profileId':intent.get('profileId'),'id': len(self.requests) + 10, 'status': 2, 'is4k': False,
                'seasons': [{'seasonNumber': n} for n in intent.get('seasons', [])]}
            media['requests'].append(saved)
            self.requests.insert(0, saved | {'media': media})
            # No downloaded media, cloud account or third-party app is touched.
            (ROOT / 'demo-request-receipts.json').write_text(json.dumps([
                {'id': row['id'], 'kind': row['media']['mediaType'], 'tmdb_id': row['media']['tmdbId'],
                 'seasons': row['seasons']} for row in self.requests]))
            return httpx.Response(201, json=saved)
        if path.startswith(('/api/v1/movie/', '/api/v1/tv/')):
            kind, identity = path.split('/')[-2:]
            key = kind + '-' + identity
            return httpx.Response(200, json=self.titles[key] | {'mediaInfo': self.media[key]})
        if path == '/api/v1/request':
            return httpx.Response(200, json={'pageInfo': {'pages': 1}, 'results': self.requests})
        if path == '/api/v1/media':
            return httpx.Response(200, json={'results': [m for m in self.media.values() if m['status'] in (4, 5)]})
        if path == '/api/v1/status':
            return httpx.Response(200, json={'version': '3.5.0-stackarr.2'})
        if path == '/api/v1/request/count':
            return httpx.Response(200, json=dict.fromkeys(('total', 'pending', 'approved', 'declined', 'processing', 'available'), 0))
        values = [value | {'mediaInfo': self.media[key]} for key, value in self.titles.items()]
        if path == '/api/v1/search':
            query = request.url.params.get('query', '').casefold()
            values = [v for v in values if query in (v.get('title') or v.get('name') or '').casefold()]
        elif path.endswith('/movies'):
            values = [v for v in values if v['mediaType'] == 'movie']
        elif path.endswith('/tv'):
            values = [v for v in values if v['mediaType'] == 'tv']
        return httpx.Response(200, json={'page': 1, 'totalPages': 1, 'results': copy.deepcopy(values)})


def build():
    catalog = Catalog()
    app = create_app(ROOT / 'demo-controller', origin=ORIGIN, transport=httpx.MockTransport(catalog.handle), background=False)
    store = app.state.store
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO account VALUES(1,?,?)', ('11' * 16, password_hash(PASSWORD, '11' * 16)))
    rev, config = store.config()
    for key in ('seerr', 'plex'):
        config.integrations[key].enabled = True
        config.integrations[key].url = 'http://' + key + '.preview.invalid'
        config.integrations[key].browser_url = ORIGIN + '/demo-' + key
    store.save(config, rev, {key: {'api_key': 'fixture-demo'} for key in ('seerr', 'plex')})
    original = app.state.home.home

    async def demo_home():
        return await original() | {'preview_notice': 'ISOLATED DESIGN PREVIEW · Progress and requests are simulated here. No real downloads or Plex account changes. Plex links open a demonstration page.'}
    app.state.home.home = demo_home

    @app.get('/demo-plex/web/index.html')
    @app.get('/demo-plex')
    def demo_plex():
        return HTMLResponse('<!doctype html><html lang="en"><head><title>Plex handoff preview</title><link rel="stylesheet" href="/static/app.css"></head><body><main class="auth-form"><section><h1>Plex handoff preview</h1><p>The title-specific Plex URL was verified against the simulated server. A real installation opens the connected Plex Web app here.</p><p>No media was played in this demonstration.</p><a href="/">Return to Stackarr</a></section></main></body></html>')

    @app.get('/demo-seerr')
    def demo_seerr():
        return HTMLResponse('<!doctype html><html lang="en"><head><title>Seerr options preview</title><link rel="stylesheet" href="/static/app.css"></head><body><main class="auth-form"><section><h1>Seerr options preview</h1><p>A connected installation opens Seerr here for approvals, request recovery, quality settings and other advanced controls.</p><p>This isolated demonstration does not contact a real account or media app.</p><a href="/">Return to Stackarr</a></section></main></body></html>')
    return app


if __name__ == '__main__':
    uvicorn.run(build(), host='127.0.0.2', port=29330, access_log=False)
