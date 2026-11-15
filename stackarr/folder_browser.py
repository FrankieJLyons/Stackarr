"""Browse only explicitly shared media directories, never the container or host root."""

from pathlib import Path, PurePosixPath, PureWindowsPath


class FolderBrowser:
    def __init__(self, roots):
        self.roots = roots
        for root in roots:
            if not Path(root['path']).is_absolute() or Path(root['path']) == Path(root['path']).parent:
                raise ValueError('Share a dedicated media folder, not a filesystem root')
            if not self.host(root['host_path']).is_absolute():
                raise ValueError('Shared media folders need an absolute host path')

    @staticmethod
    def host(value):
        return PureWindowsPath(value) if PureWindowsPath(value).drive else PurePosixPath(value)

    def resolve(self, index, relative=''):
        if index < 0 or index >= len(self.roots):
            raise ValueError('Choose one of the shared media folders')
        parts = PurePosixPath(relative)
        if parts.is_absolute() or '..' in parts.parts or '\\' in relative or ':' in relative:
            raise ValueError('Choose a folder within shared media storage')
        root = Path(self.roots[index]['path'])
        target = root / relative
        for path in (target, *target.parents):
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('Choose a direct folder, not a filesystem link')
        if not target.is_dir() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError('This folder is unavailable. Choose another folder')
        return target

    def browse(self, index=None, relative=''):
        if index is None:
            return {'roots': [{'id': i, 'name': r['label']} for i, r in enumerate(self.roots)]}
        target = self.resolve(index, relative)
        children = []
        for entry in target.iterdir():
            if len(children) >= 500:
                raise ValueError('This folder contains too many subfolders. Choose a smaller media folder')
            if entry.is_dir() and not entry.is_symlink() and not (hasattr(entry, 'is_junction') and entry.is_junction()):
                children.append({'name': entry.name, 'relative': str(PurePosixPath(relative) / entry.name)})
        return {'root': index, 'relative': relative, 'name': target.name,
                'host_path': str(self.host(self.roots[index]['host_path']) / relative),
                'folders': sorted(children, key=lambda entry: entry['name'].casefold())}

    def selected(self, host_path):
        candidate = self.host(host_path)
        for index, root in enumerate(self.roots):
            try:
                relative = candidate.relative_to(self.host(root['host_path'])).as_posix()
            except ValueError:
                continue
            return self.resolve(index, relative)
        raise ValueError('This folder is not shared with Stackarr. Choose a folder using Choose a folder, or share this folder with Stackarr first. Nothing was created.')
