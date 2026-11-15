"""Portable path planning without probing or creating host files."""

from pathlib import PurePosixPath, PureWindowsPath

from .managed_storage import folders

MEDIA_APPS = {"plex", "sonarr", "radarr", "qbittorrent"}


def layout(data_root, apps):
    selected = sorted(set(apps) & MEDIA_APPS)
    result = {"required": bool(selected), "valid": True, "problem": None,
              "folders": [], "mounts": [], "warnings": [], "host_verified": False}
    if not selected:
        return result
    windows = PureWindowsPath(data_root)
    path = windows if windows.drive or "\\" in data_root else PurePosixPath(data_root)
    if not data_root or not path.is_absolute():
        result.update(valid=False, problem="Choose a full folder address on the installation computer.")
        return result
    if ".." in path.parts or path == path.parent:
        result.update(valid=False, problem="Choose a dedicated media folder, not a drive root or a path containing '..'.")
        return result
    if str(path).startswith(("\\\\?\\", "\\\\.\\")):
        result.update(valid=False, problem="Choose a normal folder or network share, not a Windows device path.")
        return result
    names = {"media/movies": "Movies", "media/tv": "TV series", "downloads": "Downloads",
             "downloads/sonarr": "TV downloads", "downloads/radarr": "Movie downloads"}
    result["folders"] = [{"purpose": names[subpath], "host": str(path / subpath), "app": "/data/" + subpath}
                         for subpath in folders(apps)]
    result["mounts"] = [{"app": app, "host": str(path), "container": "/data",
                         "access": "read-only" if app == "plex" else "read-write"} for app in selected]
    result["warnings"].append("This is a proposed layout. Existing files are not moved and folders are not created.")
    result["warnings"].append("A shared /data mount helps avoid path mismatches. Hardlinks still depend on the filesystem, permissions and app settings.")
    if isinstance(path, PureWindowsPath):
        result["warnings"].append("Docker must be able to access this Windows folder. Drive visibility can differ for background services.")
        if path.drive.startswith("\\\\"):
            result["warnings"].append("Network shares require host and Docker access checks. Do not put database/configuration volumes on this share.")
    return result
