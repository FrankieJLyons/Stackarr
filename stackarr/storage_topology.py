"""Read-only storage evidence from host-owned Docker receipts. No mount changes."""

import os
from pathlib import Path, PurePosixPath

from pydantic import Field

from .config import Model
from .deployment import DeploymentError
from .deployment_check import differences, host_path, inspect_container, load_receipt
from .docker_names import app_project


class StorageQuery(Model):
    plex_port: int = Field(ge=1, le=65535, strict=True)
    folders: list[str] = Field(max_length=100)


def posix(value):
    if (not isinstance(value, str) or not value.startswith('/') or len(value) > 1024 or
            '\\' in value or ':' in value or any(ord(c) < 32 for c in value) or '..' in value.split('/')):
        raise ValueError('A library path is unsupported. Use a direct absolute folder.')
    return PurePosixPath(value)


def direct_directory(value):
    path = Path(value)
    if not path.is_absolute() or path == path.parent or not path.is_dir():
        raise ValueError('The library folder does not exist on the installation host.')
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked media folders require manual mapping. Existing mounts are preserved.')
    return host_path(str(path))


def host_folder(mounts, folder):
    path = posix(folder)
    matches = [mount for mount in mounts if path.is_relative_to(posix(mount['target']))]
    if not matches:
        raise ValueError('This Plex library is outside the verified shared media mounts. Share its folder with the media apps before mapping.')
    match = max(matches, key=lambda mount: len(posix(mount['target']).parts))
    return direct_directory(Path(match['source']).joinpath(*path.relative_to(posix(match['target'])).parts))


def topology(deployments, query, native=None):
    """Only recorded installations; never discover/adopt unrelated Docker containers."""
    if deployments is None:
        raise ValueError('Folder mapping needs the updated local host controller and apps installed through Stackarr.')
    with deployments.store.db() as db:
        identities = [row[0] for row in db.execute("SELECT id FROM deployments WHERE state='needs-setup' ORDER BY id LIMIT 100")]
    records = []
    for identity in identities:
        try:
            payload = load_receipt(deployments, identity)
            for key in sorted(set(payload['apps']) & {'plex', 'sonarr', 'radarr', 'qbittorrent'}):
                info = inspect_container(deployments, identity, payload, key)
                if (differences(info, app_project(identity, payload), key, payload['compose']['services'][key]) or
                        not info.get('State', {}).get('Running') or info['State'].get('Paused') or info['State'].get('Restarting')):
                    continue
                mounts = [{'source': direct_directory(host_path(m['Source'])), 'target': str(posix(m['Destination'])),
                           'writable': m.get('RW') is True} for m in info['Mounts'] if m['Type'] == 'bind']
                downloads = {}
                if key == 'qbittorrent':
                    for app in ('sonarr', 'radarr'):
                        folder = '/data/downloads/' + app
                        try:
                            downloads[app] = {'path': folder, 'host': host_folder(mounts, folder)}
                        except ValueError:
                            pass
                records.append({'app': key, 'port': int(payload['compose']['services'][key]['ports'][0]['published']),
                                'id': info['Id'], 'mounts': mounts, 'downloads': downloads})
        except (DeploymentError, ValueError, KeyError, TypeError, OSError):
            continue
    plex = [row for row in records if row['app'] == 'plex' and row['port'] == query.plex_port]
    if not plex and native and query.plex_port == 32400:
        allowed = {row['path'] for row in native['snapshot']['root_folders']}
        if not set(query.folders) <= allowed:
            raise ValueError('Native Plex libraries changed. Detect them again.')
        records.append({'app': 'plex', 'port': 32400, 'id': native['source_directory'], 'mounts': [], 'downloads': {}, 'native': True})
        paths = {folder: direct_directory(folder) for folder in query.folders}
        return {'apps': records, 'folders': paths, 'case_sensitive': os.name != 'nt'}
    if len(plex) != 1:
        raise ValueError('The connected Plex server has no verified Stackarr storage receipt. Its libraries can be read, but automatic mapping needs a verified shared installation.')
    paths = {folder: host_folder(plex[0]['mounts'], folder) for folder in query.folders}
    # Host paths use the host OS's comparison semantics even when the dashboard is Linux.
    return {'apps': records, 'folders': paths, 'case_sensitive': os.name != 'nt'}
