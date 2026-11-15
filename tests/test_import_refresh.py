import asyncio
import json

import httpx
import pytest

from stackarr.config import Config
from stackarr.import_refresh import ImportRefresh
from stackarr.store import Conflict, Store


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path)
    config = Config()
    for key in ('plex', 'radarr', 'sonarr'):
        config.integrations[key].enabled = True
        config.integrations[key].url = 'http://' + key + '.test'
    store.save(config, 1, {key: {'api_key': 'secret-' + key} for key in ('plex', 'radarr', 'sonarr')})
    state = {'event': 10, 'machine': 'claimed-server', 'fail': False, 'scans': [], 'extra': False}

    def response(request):
        app = request.url.host.split('.')[0]
        path = request.url.path
        if app == 'plex':
            assert request.headers['X-Plex-Token'] == 'secret-plex'
            if path == '/identity':
                return httpx.Response(200, json={'MediaContainer': {'claimed': True, 'machineIdentifier': state['machine']}})
            if path.endswith('/refresh'):
                assert not request.url.query
                if state['fail']:
                    return httpx.Response(503)
                state['scans'].append(path)
                return httpx.Response(200)
            return httpx.Response(200, json={'MediaContainer': {'Directory': [
                {'key': '1', 'type': 'movie', 'Location': [{'path': '/movies'}] + ([{'path': '/unrelated'}] if state['extra'] else [])},
                {'key': '2', 'type': 'show', 'Location': [{'path': '/tv'}]},
                {'key': '99', 'type': 'movie', 'Location': [{'path': '/family'}]},
            ]}})
        assert request.headers['X-Api-Key'] == 'secret-' + app
        if path.endswith('/rootfolder'):
            return httpx.Response(200, json=[{'path': '/movies' if app == 'radarr' else '/tv'}])
        assert path.endswith('/history') and request.url.params['eventType'] == '3'
        return httpx.Response(200, json={'records': [{'id': state['event'], 'eventType': 'downloadFolderImported'}]})

    return store, state, httpx.MockTransport(response)


async def enable(store, transport):
    refresh = ImportRefresh(store, transport)
    async with httpx.AsyncClient(transport=transport) as client:
        changes, notices = await refresh.review(client)
        assert len(changes) == 2 and not notices
        # Fresh account setup filters wiring by these reviewed app identities.
        assert all({c['check']['source'], c['check']['target']} <= {'plex', 'sonarr', 'radarr'} for c in changes)
        for change in changes:
            await refresh.apply(client, change)
    return refresh


async def test_new_imports_scan_only_reviewed_sections_without_manual_action(setup):
    store, state, transport = setup
    refresh = await enable(store, transport)
    await refresh.tick()
    assert not state['scans']
    state['event'] = 18  # A burst of imports coalesces to one scan per section.
    await refresh.tick()
    assert state['scans'] == ['/library/sections/2/refresh', '/library/sections/1/refresh']
    await ImportRefresh(Store(store.root), transport).tick()
    assert len(state['scans']) == 2  # Cursor survives restart; no repeated idle scans.
    state['event'] = 19
    await refresh.tick()
    assert len(state['scans']) == 2  # Rate limited while prior scan can be running.
    with store.db() as db:
        db.execute('UPDATE import_refresh SET scanned=0')
    await refresh.tick()
    assert len(state['scans']) == 4


async def test_failed_scan_keeps_pending_import_across_restart(setup):
    store, state, transport = setup
    refresh = await enable(store, transport)
    state.update(event=11, fail=True)
    await refresh.tick()
    with store.db() as db:
        assert {r[0] for r in db.execute('SELECT cursor FROM import_refresh')} == {10}
    state['fail'] = False
    await ImportRefresh(Store(store.root), transport).tick()
    assert len(state['scans']) == 2


@pytest.mark.parametrize('changed', ['machine', 'extra', 'credential', 'disabled', 'url'])
async def test_changed_destination_or_scope_never_scans(setup, changed):
    store, state, transport = setup
    refresh = await enable(store, transport)
    state['event'] = 11
    if changed == 'machine':
        state['machine'] = 'another-server'
    elif changed == 'extra':
        state['extra'] = True
        # Both apps blocked here to assert zero writes for scope drift.
        revision, config = store.config()
        config.integrations['sonarr'].enabled = False
        store.save(config, revision)
    else:
        revision, config = store.config()
        for app in ('sonarr', 'radarr'):
            if changed == 'disabled':
                config.integrations[app].enabled = False
            if changed == 'url':
                config.integrations[app].url = 'http://another.test'
        store.save(config, revision, {'plex': {'api_key': 'rotated'}} if changed == 'credential' else {})
    await refresh.tick()
    assert not state['scans']


async def test_import_between_review_and_apply_is_not_lost(setup):
    store, state, transport = setup
    refresh = ImportRefresh(store, transport)
    async with httpx.AsyncClient(transport=transport) as client:
        changes, _ = await refresh.review(client)
        state['event'] = 11
        for change in changes:
            await refresh.apply(client, change)
        assert (await refresh.review(client))[0] == []
    await refresh.tick()
    assert len(state['scans']) == 2
    with store.db() as db:
        raw = json.dumps(db.execute('SELECT * FROM import_refresh').fetchall())
    assert 'secret-' not in raw


async def test_reviewed_server_change_blocks_apply(setup):
    store, state, transport = setup
    refresh = ImportRefresh(store, transport)
    async with httpx.AsyncClient(transport=transport) as client:
        changes, _ = await refresh.review(client)
        state['machine'] = 'different'
        with pytest.raises(Conflict):
            await refresh.apply(client, changes[0])
    assert not state['scans']


async def test_worker_survives_transient_storage_error(setup, monkeypatch):
    store, _, transport = setup
    refresh = ImportRefresh(store, transport)
    attempts = []

    async def tick():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('Storage temporarily unavailable')
        raise asyncio.CancelledError

    async def sleep(seconds):
        assert seconds == 15

    monkeypatch.setattr(refresh, 'tick', tick)
    monkeypatch.setattr('stackarr.import_refresh.asyncio.sleep', sleep)
    with pytest.raises(asyncio.CancelledError):
        await refresh.work()
    assert len(attempts) == 2


async def test_unconfigured_startup_and_review_do_not_change_update_fingerprint(setup):
    from stackarr.self_update import fingerprint

    store, _, transport = setup
    before = fingerprint(store.root)
    refresh = ImportRefresh(store, transport)
    await refresh.tick()
    async with httpx.AsyncClient(transport=transport) as client:
        assert len((await refresh.review(client))[0]) == 2
    assert fingerprint(store.root) == before


async def test_update_checks_preserve_discovery_scope_but_allow_live_progress(setup):
    from stackarr.self_update import fingerprint

    store, state, transport = setup
    refresh = await enable(store, transport)
    before = fingerprint(store.root)
    state['event'] = 11
    await refresh.tick()
    assert fingerprint(store.root) == before
    with store.db() as db:
        db.execute("UPDATE import_refresh SET scope='{}' WHERE app='radarr'")
    assert fingerprint(store.root) != before
