"""Exercise real preset routes and UI against isolated synthetic Sonarr/Radarr."""

import argparse
import copy
import json
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import expect, sync_playwright

from stackarr.server import create_app, password_hash
from tests.test_quality_rules import Arr
from tools.browser_check import capture_browser_failure


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='stackarr-presets-') as temporary:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        origin = f'http://127.0.0.1:{port}'
        apps = {}

        def respond(request):
            key = request.url.host.removesuffix('.test')
            assert key in apps, 'Only synthetic library apps are allowed'
            return apps[key].respond(request)

        app = create_app(Path(temporary), origin=origin, transport=httpx.MockTransport(respond), background=False)
        store = app.state.store
        revision, config = store.config()
        for key in ('sonarr', 'radarr'):
            config.integrations[key].enabled = True
            config.integrations[key].url = f'http://{key}.test'
            apps[key] = Arr(store, key)
        store.save(config, revision, {key: {'api_key': 'synthetic-key'} for key in apps})
        password, salt = 'synthetic browser password', secrets.token_hex(16)
        with store.db() as db:
            db.execute('INSERT INTO account VALUES(1,?,?)', (salt, password_hash(password, salt)))
        before = {key: copy.deepcopy((arr.profiles, arr.titles)) for key, arr in apps.items()}
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as playwright, capture_browser_failure(lambda: page, output):
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1050}, reduced_motion='reduce')
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin)
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Sign in →', exact=True).click()
                page.locator('.control-tabs [data-view="settings"]').click()
                page.locator('[data-settings-section="recommended"]').click()
                expect(page.get_by_role('heading', name='Everyday 1080p', exact=True)).to_be_visible()
                assert not apps['sonarr'].writes
                page.screenshot(path=str(output / 'recommended-desktop.png'), full_page=True)
                for width, name in [(390, 'phone'), (768, 'tablet')]:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output / f'recommended-{name}.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1050})
                page.locator('[data-quality-preset="everyday-1080p"]').click()
                expect(page.get_by_role('button', name='Save rules for new requests', exact=True)).to_be_visible()
                assert not apps['sonarr'].writes
                expect(page.locator('.preset-customize')).not_to_have_attribute('open', '')
                assert page.locator('[aria-label="Quality rule preview"] li').count() == 1
                page.screenshot(path=str(output / 'preview-1080p.png'), full_page=True)
                page.get_by_role('button', name='Save rules for new requests', exact=True).click()
                expect(page.get_by_role('button', name='Preview restore previous rules', exact=True)).to_be_visible()
                assert len(apps['sonarr'].writes) == 1
                page.get_by_role('button', name='Preview restore previous rules', exact=True).click()
                expect(page.locator('[aria-label="Quality rule preview"]')).to_contain_text('Pause rules')
                page.get_by_role('button', name='Save rules for new requests', exact=True).click()
                page.wait_for_function('() => !qualityState.busy')
                assert not app.state.home.rules.saved('sonarr')[1].enabled
                page.get_by_label('Choose a library app', exact=True).select_option('radarr')
                page.locator('[data-quality-preset="smaller-720p"]').click()
                expect(page.locator('[aria-label="Quality rule preview"]')).to_contain_text('720p')
                assert not apps['radarr'].writes
                page.get_by_role('button', name='Save rules for new requests', exact=True).click()
                page.wait_for_function('() => !qualityState.busy')
                assert len(apps['radarr'].writes) == 1
                assert app.state.home.rules.saved('radarr')[1].newer == '720p'
                for key, arr in apps.items():
                    assert arr.profiles[:1] == before[key][0] and arr.titles == before[key][1]
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    report = {'passed': True, 'scope': 'Real API and assets, isolated synthetic apps only',
              'cases': ['preview-before-write', 'single-profile-only', 'sonarr-1080p-apply',
                        'restore-paused-rules', 'radarr-720p-apply', 'original-profiles-and-titles-preserved',
                        'phone-tablet-desktop', 'no-browser-errors']}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(check(parser.parse_args().output)))
