"""Download and verify the pinned Windows gateway for packaging and CI."""

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path


def prepare(output):
    lock = json.loads((Path(__file__).resolve().parents[1] / 'stackarr/caddy.lock.json').read_text())
    if not lock['url'].startswith('https://github.com/caddyserver/caddy/releases/download/'):
        raise ValueError('Expected the official pinned Caddy release')
    with urllib.request.urlopen(lock['url'], timeout=120) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != lock['archive_sha256']:
        raise ValueError('Caddy archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        binary = archive.read('caddy.exe')
        license_text = archive.read('LICENSE')
    if hashlib.sha256(binary).hexdigest() != lock['binary_sha256']:
        raise ValueError('Caddy executable checksum mismatch')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'caddy.exe').write_bytes(binary)
    (output / 'LICENSE').write_bytes(license_text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    prepare(parser.parse_args().output)
