"""Plex protocol simulator for native import/Seerr component acceptance.

Never proxies or contacts a Plex server. Metadata is synthetic and is exposed
only after an Arr refresh callback and the corresponding original files exist.
No authentication headers, tokens, queries or account identity are logged.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path('/state')
MEDIA = Path('/media')
MACHINE = 'stackarr-simulated-import-protocol'
LOCK = threading.Lock()
REFRESHED = set()
if (ROOT / 'protocol-events.jsonl').exists():
    for line in (ROOT / 'protocol-events.jsonl').read_text().splitlines():
        try:
            event = json.loads(line)
            if event['path'].endswith('/refresh'):
                REFRESHED.add(event['section'])
        except (ValueError, KeyError):
            pass


def items(section):
    count = len(list((MEDIA / 'media' / ('movies' if section == '1' else 'tv')).rglob('*.mp4')))
    if section not in REFRESHED:
        return []
    common = {'addedAt': int(time.time()), 'Media': [{'videoResolution': '720', 'Part': []}]}
    if section == '1':
        return [{**common, 'ratingKey': 'import-movie', 'type': 'movie', 'title': 'Original movie protocol fixture',
                 'guid': 'tmdb://10331'}] if count else []
    return [{**common, 'ratingKey': f'import-episode-{index}', 'type': 'episode',
             'grandparentRatingKey': 'import-show', 'parentRatingKey': 'import-season-1',
             'parentIndex': 1, 'index': index, 'title': f'Original episode {index}'}
            for index in range(1, min(count, 6) + 1)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.send({'simulation': True})
        keys = json.loads((ROOT / 'protocol-keys-private.json').read_text())
        query = parse_qs(urlsplit(self.path).query)
        token = self.headers.get('X-Plex-Token') or query.get('X-Plex-Token', [''])[0]
        if token not in keys:
            return self.send({'MediaContainer': {'error': 'Synthetic protocol authentication required'}}, 401)
        product = self.headers.get('X-Plex-Product') or query.get('X-Plex-Product', ['Seerr'])[0]
        product = product if product in {'Sonarr', 'Radarr', 'Seerr'} else 'Other'
        section = path.split('/')[3] if path.startswith('/library/sections/') else None
        with LOCK:
            with (ROOT / 'protocol-events.jsonl').open('a') as stream:
                stream.write(json.dumps({'at': time.time(), 'path': path, 'app': product,
                    'section': section, 'simulation': True}) + '\n')
            if path.endswith('/refresh'):
                REFRESHED.add(section)
        if path in {'/', '/identity'}:
            return self.send({'MediaContainer': {'size': 0, 'machineIdentifier': MACHINE, 'claimed': True,
                'friendlyName': 'SIMULATED Plex import protocol', 'version': '1.43.4.10903-fixture'}})
        if path == '/library/sections':
            return self.send({'MediaContainer': {'size': 2, 'Directory': [
                {'key': '1', 'title': 'Simulated Movies', 'type': 'movie', 'agent': 'tv.plex.agents.movie',
                 'Location': [{'path': '/data/media/movies'}]},
                {'key': '2', 'title': 'Simulated TV', 'type': 'show', 'agent': 'tv.plex.agents.series',
                 'Location': [{'path': '/data/media/tv'}]},
            ]}})
        if path.endswith('/refresh'):
            return self.send({'MediaContainer': {'size': 0}})
        if section in {'1', '2'} and path.endswith('/all'):
            data = items(section)
            return self.send({'MediaContainer': {'size': len(data), 'totalSize': len(data), 'Metadata': data}})
        if path == '/library/metadata/import-show':
            return self.send({'MediaContainer': {'size': 1, 'Metadata': [{
                'ratingKey': 'import-show', 'type': 'show', 'title': 'Original season protocol fixture',
                'guid': 'themoviedb://2316', 'addedAt': int(time.time()),
                'Children': {'Metadata': [{'index': 1, 'ratingKey': 'import-season-1'}]},
            }]}})
        if path == '/library/metadata/import-season-1/children':
            data = items('2')
            return self.send({'MediaContainer': {'size': len(data), 'Metadata': data}})
        return self.send({'MediaContainer': {'size': 0, 'Metadata': []}}, 404)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
