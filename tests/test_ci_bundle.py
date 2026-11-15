import hashlib
import json
import zipfile

import pytest

from tools import prepare_ci_bundled as ci


def bundle(tmp_path, *, duplicate=False, checksum=True, image_hash=True):
    archive = tmp_path / 'release.zip'
    payload = b'synthetic image archive'
    manifest = {'bundled_app_images': [{'image': 'pinned'}],
                'files': {'stackarr-image.tar': hashlib.sha256(payload).hexdigest() if image_hash else 'changed'}}
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('release/manifest.json', json.dumps(manifest))
        output.writestr('release/stackarr-image.tar', payload)
        if duplicate:
            output.writestr('another/manifest.json', json.dumps(manifest))
    receipt = tmp_path / 'release.zip.sha256'
    receipt.write_text((hashlib.sha256(archive.read_bytes()).hexdigest() if checksum else 'changed') + '  release.zip\n')
    return archive, receipt


@pytest.mark.parametrize('options', [{'duplicate': True}, {'checksum': False}, {'image_hash': False}])
def test_changed_or_ambiguous_bundle_never_reaches_docker(tmp_path, monkeypatch, options):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setattr(ci, 'catalog', lambda: {'seerr': {'image': 'pinned'}})
    monkeypatch.setattr(ci.subprocess, 'run', lambda *a, **k: pytest.fail('Invalid bundle reached Docker'))
    with pytest.raises(ValueError):
        ci.prepare(*bundle(tmp_path, **options))


def test_bundle_remains_restricted_to_disposable_ci(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(ValueError, match='GitHub Actions'):
        ci.prepare(*bundle(tmp_path))
