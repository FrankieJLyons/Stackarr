"""Test presets on a disposable pinned Cleanuparr, with synthetic companion apps."""

import argparse
import asyncio
import json
import secrets
import subprocess
import time
from pathlib import Path

import httpx

from stackarr.cleanup_presets import CleanupPresets, Intent
from stackarr.store import Store
from tests.test_cleanup_presets import Apps, configure
from tools.lan_gateway_check import snapshot


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, encoding='utf-8').strip()


class Routing(httpx.AsyncBaseTransport):
    def __init__(self, origin, fake):
        self.origin, self.fake = origin, fake

    async def handle_async_request(self, request):
        if str(request.url).startswith(self.origin + '/'):
            async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
                response = await client.request(request.method, request.url, headers=request.headers, content=request.content)
                headers = {key: value for key, value in response.headers.items() if key not in ('content-encoding', 'content-length')}
                return httpx.Response(response.status_code, headers=headers, content=response.content)
        return self.fake.respond(request)


def check(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    config_dir = output / 'native-config'
    config_dir.mkdir()
    image = json.loads(Path('stackarr/images.lock.json').read_text())['images']['cleanuparr']
    name = 'stackarr-cleanup-preset-check-' + secrets.token_hex(4)
    docker('run', '-d', '--rm', '--name', name, '--label', 'io.stackarr.test=cleanup-presets',
           '-p', '127.0.0.1::11011', '--mount', f'type=bind,source={config_dir},target=/config', image)
    try:
        port = json.loads(docker('inspect', name))[0]['NetworkSettings']['Ports']['11011/tcp'][0]['HostPort']
        origin = 'http://127.0.0.1:' + port
        with httpx.Client(base_url=origin, trust_env=False, timeout=15) as client:
            for _ in range(120):
                try:
                    if client.get('/api/auth/status').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            password = secrets.token_urlsafe(32)
            client.post('/api/auth/setup/account', json={'username': 'preset-check', 'password': password}).raise_for_status()
            client.post('/api/auth/setup/complete').raise_for_status()
            response = client.post('/api/auth/login', json={'username': 'preset-check', 'password': password})
            response.raise_for_status()
            client.headers['Authorization'] = 'Bearer ' + response.json()['tokens']['accessToken']
            key = client.get('/api/account/api-key').json()['apiKey']
            general = client.get('/api/configuration/general').json()
            client.put('/api/configuration/general', json=general | {'dryRun': True, 'statusCheckEnabled': False}).raise_for_status()
            for app in ('sonarr', 'radarr'):
                client.post('/api/configuration/' + app + '/instances', json={
                    'name': 'Synthetic ' + app, 'url': f'http://{app}.test', 'apiKey': 'PRIVATE-api',
                    'version': 4 if app == 'sonarr' else 6, 'enabled': True}).raise_for_status()
            client.post('/api/configuration/download_client', json={
                'name': 'Synthetic qBittorrent', 'host': 'http://qbittorrent.test:8080', 'typeName': 'qBittorrent',
                'enabled': True, 'username': 'test', 'password': 'PRIVATE-password'}).raise_for_status()
        store = Store(output / 'synthetic-stackarr')
        configure(store)
        revision, config = store.config()
        config.integrations['cleanuparr'].url = origin
        store.save(config, revision, {'cleanuparr': {'api_key': key}})
        fake = Apps(store)
        feature = CleanupPresets(store, Routing(origin, fake))

        async def exercise():
            baseline = await feature.snapshot()
            results = []
            for preset in ('observe', 'media', 'recover', 'completed'):
                status = await feature.status()
                category = status['imported_categories'][0]
                intent = Intent(preset=preset, connectivity_url='https://check.example',
                                client_id=category['client_id'], category=category['category'])
                plan = await feature.review(intent)
                result = await feature.apply(plan)
                assert result['state'] == 'applied', (preset, result, [(op['key'], op.get('state')) for op in feature.run(result['id'])['ops']])
                assert (await feature.snapshot())['general']['dryRun'] is True
                restored = await feature.apply(await feature.restore_review(result['id']))
                assert restored['state'] == 'applied', (preset, restored)
                assert await feature.snapshot() == baseline, preset
                results.append(preset)
            return results

        cases = asyncio.run(exercise())
    finally:
        docker('stop', '--time', '5', name)
    assert snapshot() == before, 'Existing containers changed during isolated acceptance'
    report = {'passed': True, 'image': image, 'presets': cases, 'existing_containers_unchanged': True,
              'scope': 'Disposable pinned Cleanuparr API; synthetic Arr/qBittorrent; dry-run only; no household app writes'}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(check(parser.parse_args().output)))
