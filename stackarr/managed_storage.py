"""Create only the fixed, reviewed layout; never move media or change permissions."""

from pathlib import Path


def folders(apps):
    selected = set(apps)
    result = []
    if selected & {"plex", "radarr"}:
        result.append("media/movies")
    if selected & {"plex", "sonarr"}:
        result.append("media/tv")
    if "qbittorrent" in selected:
        result.append("downloads")
        result.extend("downloads/" + key for key in ("sonarr", "radarr") if key in selected)
    return result


def prepare(data_root, apps):
    wanted = folders(apps)
    if not wanted:
        return
    root = Path(data_root)
    if not root.is_absolute() or root == root.parent or ".." in root.parts or not root.is_dir():
        raise ValueError("Choose an existing dedicated media folder before installing.")

    def verify(path):
        for candidate in (path, *path.parents):
            if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
                raise ValueError("Media layout contains a filesystem link. Choose a direct folder before resuming.")
            if candidate.exists() and not candidate.is_dir():
                raise ValueError("A required media folder is occupied by a file. Existing files are preserved.")

    # Check the entire layout before creating anything. No deletion, chmod or chown.
    for relative in wanted:
        verify(root / relative)
    for relative in wanted:
        current = root
        for part in Path(relative).parts:
            current = current / part
            verify(current)
            current.mkdir(exist_ok=True)
