import pytest
from fastapi.testclient import TestClient

from stackarr.folder_browser import FolderBrowser
from stackarr.server import create_app


def test_browse_only_shared_directories_and_map_host_paths(tmp_path):
    media = tmp_path / 'shared'
    media.mkdir()
    (media / 'Movies').mkdir()
    (media / 'private-file.txt').write_text('not listed')
    browser = FolderBrowser([{'path': str(media), 'host_path': 'D:\\Media', 'label': 'Media disk'}])
    assert browser.browse()['roots'] == [{'id': 0, 'name': 'Media disk'}]
    row = browser.browse(0)
    assert row['folders'] == [{'name': 'Movies', 'relative': 'Movies'}]
    assert browser.browse(0, 'Movies')['host_path'] == 'D:\\Media\\Movies'
    assert browser.selected('D:\\Media\\Movies') == media / 'Movies'
    for relative in ('../', '/etc', 'C:/Windows', '..\\secret'):
        with pytest.raises(ValueError):
            browser.browse(0, relative)
    with pytest.raises(ValueError):
        browser.selected('D:\\Other')
    with pytest.raises(ValueError):
        browser.browse(-1)


def test_folder_creation_needs_auth_current_revision_and_shared_root(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    sentinel = media / 'keep.txt'
    sentinel.write_text('preserve')
    app = create_app(tmp_path / 'state', origin='http://testserver', background=False,
                     media_roots=[{'path': str(media), 'host_path': str(media), 'label': 'Media'}])
    with TestClient(app) as client:
        assert client.get('/api/onboarding/folders').status_code == 401
        token = (app.state.store.root / 'setup-token').read_text()
        client.post('/api/setup', json={'password': 'synthetic password', 'setup_token': token}, headers={'Origin': 'http://testserver'})
        login = client.post('/api/login', json={'password': 'synthetic password'}, headers={'Origin': 'http://testserver'})
        headers = {'Origin': 'http://testserver', 'X-CSRF-Token': login.json()['csrf']}
        draft = {'apps': ['plex'], 'data_root': str(media)}
        saved = client.put('/api/onboarding', json={'revision': 1, 'draft': draft}, headers=headers)
        assert saved.status_code == 200
        revision = saved.json()['revision']
        assert client.post('/api/onboarding/prepare-folders', json={'revision': revision}).status_code == 403
        assert client.post('/api/onboarding/prepare-folders', json={'revision': revision - 1}, headers=headers).status_code == 409
        assert client.post('/api/onboarding/prepare-folders', json={'revision': revision}, headers=headers).status_code == 200
        assert (media / 'media/movies').is_dir()
        assert (media / 'media/tv').is_dir()
        assert not (media / 'downloads').exists()
        assert sentinel.read_text() == 'preserve'
        draft['data_root'] = str(tmp_path)
        client.put('/api/onboarding', json={'revision': revision, 'draft': draft}, headers=headers)
        rejected = client.post('/api/onboarding/prepare-folders', json={'revision': revision + 1}, headers=headers)
        assert rejected.status_code == 422
        assert 'not shared with Stackarr' in rejected.json()['detail']


def test_folder_browser_rejects_links(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    external = tmp_path / 'outside'
    external.mkdir()
    try:
        (root / 'escape').symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip('Filesystem links unavailable')
    browser = FolderBrowser([{'path': str(root), 'host_path': str(root), 'label': 'Media'}])
    assert browser.browse(0)['folders'] == []
    with pytest.raises(ValueError):
        browser.browse(0, 'escape')
