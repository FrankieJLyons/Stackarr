"""Real UI/API cleanup checks with synthetic apps; never contacts household apps."""

import argparse
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
from tests.test_cleanup_presets import Apps, configure
from tools.browser_check import capture_browser_failure


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='stackarr-cleanup-ui-') as temporary:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        origin = f'http://127.0.0.1:{port}'
        remote = None
        app = create_app(Path(temporary), origin=origin,
                         transport=httpx.MockTransport(lambda request: remote.respond(request)), background=False)
        store = app.state.store
        configure(store)
        remote = Apps(store)
        password, salt = 'synthetic browser password', secrets.token_hex(16)
        with store.db() as db:
            db.execute('INSERT INTO account VALUES(1,?,?)', (salt, password_hash(password, salt)))
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
                page.get_by_role('button', name='Check Cleanuparr', exact=True).click()
                expect(page.get_by_label('Choose a preset', exact=True)).to_have_value('observe')
                page.get_by_role('button', name='Preview preset', exact=True).click()
                expect(page.get_by_role('heading', name='Review Observe first', exact=True)).to_be_visible()
                assert not remote.writes
                page.screenshot(path=str(output / 'observe-preview.png'), full_page=True)
                page.get_by_role('button', name='Apply in dry-run', exact=True).click()
                page.wait_for_function('() => !cleanupState.busy')
                assert remote.data['general']['dryRun'] is True
                assert remote.data['queue_cleaner']['enabled'] is True
                assert not page.locator('[data-cleanup-live]').count()
                page.get_by_label('Choose a preset', exact=True).select_option('recover')
                page.get_by_label('HTTPS internet-check URL', exact=True).fill('https://check.example')
                page.get_by_role('button', name='Preview preset', exact=True).click()
                page.get_by_role('button', name='Apply in dry-run', exact=True).click()
                page.wait_for_function('() => !cleanupState.busy')
                history = app.state.cleanup_presets.history()
                recovery = next(row['id'] for row in history if row['preset'] == 'recover')
                page.get_by_text('Saved Cleanuparr changes & recovery', exact=True).click()
                page.locator('[data-cleanup-live]').click()
                expect(page.get_by_role('heading', name='Confirm live cleanup', exact=True)).to_be_visible()
                submit = page.get_by_role('button', name='Enable live cleanup', exact=True)
                expect(submit).to_be_disabled()
                assert remote.data['general']['dryRun'] is True
                page.locator('#cleanup-live-ack').check()
                page.get_by_label('Type ENABLE LIVE DELETION to confirm', exact=True).fill('enable live deletion')
                expect(submit).to_be_disabled()
                page.get_by_label('Type ENABLE LIVE DELETION to confirm', exact=True).fill('ENABLE LIVE DELETION')
                expect(submit).to_be_enabled()
                page.screenshot(path=str(output / 'separate-live-confirmation.png'), full_page=True)
                submit.click()
                page.wait_for_function('() => !cleanupState.busy')
                assert remote.data['general']['dryRun'] is False
                page.get_by_text('Saved Cleanuparr changes & recovery', exact=True).click()
                page.locator(f'[data-cleanup-restore="{recovery}"]').click()
                page.get_by_role('button', name='Restore in dry-run', exact=True).click()
                page.wait_for_function('() => !cleanupState.busy')
                assert remote.data['general']['dryRun'] is True and not remote.data['stall']
                # Check capability blockers and preserve the selected recipe across a refresh.
                remote.post_category = ''
                page.get_by_role('button', name='Check settings again', exact=True).click()
                page.wait_for_function('() => !cleanupState.busy')
                page.get_by_label('Choose a preset', exact=True).select_option('completed')
                expect(page.get_by_role('button', name='Preview preset', exact=True)).to_be_disabled()
                expect(page.locator('#cleanup-presets')).to_contain_text('post-import category')
                page.get_by_label('Choose a preset', exact=True).select_option('observe')
                for width, name in [(390, 'phone'), (768, 'tablet'), (1440, 'desktop')]:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output / f'cleanup-{name}.png'), full_page=True)
                page.locator('[data-settings-section="appearance"]').click()
                page.get_by_label('Appearance', exact=True).select_option('light')
                page.get_by_role('button', name='Save settings', exact=True).click()
                page.wait_for_function('() => !state.dirty')
                page.locator('[data-settings-section="recommended"]').click()
                page.screenshot(path=str(output / 'cleanup-light.png'), full_page=True)
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    report = {'passed': True, 'scope': 'Real API/UI with isolated synthetic apps only',
              'cases': ['observe-default', 'preview-before-write', 'apply-in-dry-run', 'independent-live-review',
                        'checkbox-and-exact-confirmation', 'restore-without-restoring-live-mode',
                        'missing-post-import-category-blocker', 'phone-tablet-desktop-light-dark']}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(check(parser.parse_args().output)))
