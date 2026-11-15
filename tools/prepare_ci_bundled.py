"""Load pinned bundled app images from a verified release on a disposable CI runner."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from stackarr.bundled_images import catalog, verify


def prepare(path, checksum):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('Bundled CI image loading is restricted to GitHub Actions runners')
    fields = checksum.read_text(encoding='ascii').strip().split()
    if len(fields) != 2 or fields[1] != path.name:
        raise ValueError('CI checksum must name the selected release archive')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != fields[0]:
            raise ValueError('CI bundle does not match its release checksum')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifests = [name for name in names if name.endswith('/manifest.json') and name.count('/') == 1]
        if len(manifests) != 1 or len(names) != len(set(names)):
            raise ValueError('CI bundle must contain one unambiguous package manifest')
        prefix = manifests[0].removesuffix('manifest.json')
        manifest = json.loads(archive.read(manifests[0]))
        expected = {row['image'] for row in catalog().values()}
        if {row['image'] for row in manifest['bundled_app_images']} != expected:
            raise ValueError('CI bundle does not contain the reviewed app images')
        with tempfile.TemporaryDirectory(prefix='stackarr-ci-images-') as folder:
            image = Path(folder) / 'image.tar'
            with archive.open(prefix + 'stackarr-image.tar') as source, image.open('wb') as target:
                shutil.copyfileobj(source, target)
            with image.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['files']['stackarr-image.tar']:
                    raise ValueError('CI image archive integrity check failed')
            subprocess.run(['docker', 'load', '--input', str(image)], check=True, timeout=240)
    for reference in expected:
        verify(lambda args: subprocess.check_output(['docker', *args], text=True), reference)
    print('Reviewed bundled app images loaded and verified; no containers started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('checksum', type=Path)
    args = parser.parse_args()
    prepare(args.archive, args.checksum)
