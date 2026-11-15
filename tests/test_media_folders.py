import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from stackarr.controller import InstallationController
from stackarr.controller_transport import ControllerClient, ControllerConnectionError, create_controller_app
from stackarr.media_folders import choose, grant
from stackarr.store import Conflict, Store


def test_host_selected_folder_is_persistent_and_refs_never_shift(tmp_path):
    first, second = tmp_path / "First folder", tmp_path / "Media with spaces – 电影"
    first.mkdir()
    second.mkdir()
    store = Store(tmp_path / "state")
    roots = [{"path": str(first), "host_path": str(first), "label": "First"}]
    controller = InstallationController(store, roots, 28000, folder_chooser=lambda: str(second))
    selected = controller.media_folder()
    assert selected == {"cancelled": False, "path": str(second), "root": 1, "relative": ""}
    assert controller.folders(0)["host_path"] == str(first)
    restarted = InstallationController(store, [], 28000)
    assert restarted.folders(1)["host_path"] == str(second)
    assert restarted.folders(0)["host_path"] == str(first)
    assert controller.media_folder()["root"] == 1
    assert len(controller.folders()["roots"]) == 2
    assert not store.config()[1].storage.data_root and not controller.deployments.rows()


def test_cancel_preserves_previous_root_and_settings(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    controller = InstallationController(Store(tmp_path / "state"),
        [{"path": str(root), "host_path": str(root), "label": "Media"}], 28000, folder_chooser=lambda: "")
    before = controller.store.config()
    assert controller.media_folder() == {"cancelled": True}
    assert controller.folders()["roots"] == [{"id": 0, "name": "Media"}]
    assert controller.store.config() == before


def test_bad_folder_is_never_granted(tmp_path):
    store = Store(tmp_path / "state")
    for path in (tmp_path / "missing", tmp_path.anchor):
        with pytest.raises(ValueError):
            grant(store, path)
    assert InstallationController(store, [], 28000).folders() == {"roots": []}


def test_folder_dialog_is_single_flight(tmp_path):
    started, release = threading.Event(), threading.Event()
    def picker():
        started.set()
        assert release.wait(5)
        return ""
    controller = InstallationController(Store(tmp_path), [], 28000, folder_chooser=picker)
    worker = threading.Thread(target=controller.media_folder)
    worker.start()
    try:
        assert started.wait(5)
        with pytest.raises(Conflict, match="already open"):
            controller.media_folder()
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()


async def test_signed_picker_endpoint_rejects_browser_paths(tmp_path):
    calls = []
    controller = InstallationController(Store(tmp_path), [], 28000, folder_chooser=lambda: calls.append("opened") or "")
    key = b"x" * 32
    app = create_controller_app(controller, key, "127.0.0.1:28010", run_worker=False)
    client = ControllerClient("http://127.0.0.1:28010", key, httpx.ASGITransport(app=app))
    with pytest.raises(ControllerConnectionError):
        await client.request("media-folder", {"path": "C:/"})
    assert not calls
    assert await client.request("media-folder", {}) == {"cancelled": True}
    assert calls == ["opened"]


@pytest.mark.parametrize("path", ["", "C:/Media with spaces – 电影"])
def test_windows_picker_returns_native_selection_without_a_console(monkeypatch, path):
    if os.name != "nt":
        with pytest.raises(ValueError):
            choose()
        return
    def run(arguments, **options):
        assert arguments[1:3] == ["-m", "stackarr.media_folders"]
        assert options["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert options["timeout"] == 180 and options["stdin"] == subprocess.DEVNULL
        Path(arguments[-1]).write_text(json.dumps({"path": path}), encoding="utf-8")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("stackarr.media_folders.subprocess.run", run)
    assert choose() == path


@pytest.mark.skipif(os.name != "nt", reason="Windows native helper")
@pytest.mark.parametrize("content", [None, "not JSON", '{"path": []}', '{"path": "", "other": true}', "x" * 8193])
def test_native_picker_rejects_missing_or_invalid_result(monkeypatch, content):
    def run(arguments, **options):
        if content is not None:
            Path(arguments[-1]).write_text(content, encoding="utf-8")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("stackarr.media_folders.subprocess.run", run)
    with pytest.raises(ValueError, match="previous folder is unchanged"):
        choose()
