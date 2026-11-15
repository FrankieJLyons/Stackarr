import json

import httpx
import pytest

from stackarr.bootstrap import download_categories, libraries
from stackarr.managed_storage import prepare


def test_layout_preserves_media_and_only_creates_selected_folders(tmp_path):
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("existing media")
    prepare(str(tmp_path), ["sonarr"])
    prepare(str(tmp_path), ["sonarr"])
    assert (tmp_path / "media/tv").is_dir()
    assert not (tmp_path / "media/movies").exists()
    assert not (tmp_path / "downloads").exists()
    assert sentinel.read_text() == "existing media"


def test_conflicting_file_prevents_partial_layout(tmp_path):
    (tmp_path / "downloads").write_text("keep me")
    with pytest.raises(ValueError, match="occupied"):
        prepare(str(tmp_path), ["plex", "qbittorrent"])
    assert not (tmp_path / "media").exists()
    assert (tmp_path / "downloads").read_text() == "keep me"


def test_linked_media_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "media").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not allow creating symlinks")
    with pytest.raises(ValueError, match="link"):
        prepare(str(root), ["sonarr"])
    assert not list(outside.iterdir())


def test_library_setup_recovers_lost_response_without_duplicate_write(monkeypatch):
    rows, writes = [], []
    def respond(request):
        assert request.url.path == "/api/v3/rootfolder"
        if request.method == "GET":
            return httpx.Response(200, json=rows)
        row = json.loads(request.content)
        rows.append(row)
        writes.append(row)
        raise httpx.ReadError("synthetic lost response")
    client = httpx.Client
    monkeypatch.setattr("stackarr.bootstrap.httpx.Client", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    payload = {"apps": ["sonarr"], "compose": {"services": {"sonarr": {"ports": [{"published": "38989"}]}}}}
    with pytest.raises(ValueError, match="media folder"):
        libraries(payload, {"sonarr": {"api_key": "synthetic"}})
    libraries(payload, {"sonarr": {"api_key": "synthetic"}})
    assert writes == [{"path": "/data/media/tv"}]


def test_download_categories_recover_without_duplicates_and_preserve_changed_paths(monkeypatch):
    rows, writes = {}, []
    from urllib.parse import parse_qs

    def respond(request):
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, text="Ok.")
        if request.method == "GET":
            return httpx.Response(200, json=rows)
        values = parse_qs(request.content.decode())
        key, path = values["category"][0], values["savePath"][0]
        rows[key] = {"name": key, "savePath": path}
        writes.append(key)
        raise httpx.ReadError("synthetic lost response")

    client = httpx.Client
    monkeypatch.setattr("stackarr.bootstrap.httpx.Client", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    payload = {"apps": ["qbittorrent", "sonarr"], "compose": {"services": {"qbittorrent": {"ports": [{"published": "38080"}]}}}}
    saved = {"qbittorrent": {"username": "admin", "password": "synthetic"}}
    with pytest.raises(ValueError, match="categories"):
        download_categories(payload, saved)
    download_categories(payload, saved)
    assert writes == ["sonarr"]
    rows["sonarr"]["savePath"] = "/changed"
    with pytest.raises(ValueError, match="preserved"):
        download_categories(payload, saved)
    assert rows["sonarr"]["savePath"] == "/changed"
