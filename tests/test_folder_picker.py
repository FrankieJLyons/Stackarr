import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from stackarr.folder_picker import FolderPicker
from stackarr.server import create_app


def test_native_selection_has_one_consumer_and_preserves_cancel():
    picker = FolderPicker()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(picker.request)
        ticket = None
        for _ in range(100):
            ticket = picker.take()
            if ticket:
                break
            threading.Event().wait(.005)
        assert ticket
        assert picker.take() is None
        with pytest.raises(ValueError, match="already open"):
            picker.request(timeout=.001)
        picker.complete(ticket, "")
        assert future.result(timeout=1) == ""
    assert picker.current is None


def test_timeout_does_not_deliver_late_selection_to_a_later_request():
    picker = FolderPicker()
    with pytest.raises(ValueError, match="timed out"):
        picker.request(timeout=.001)
    assert picker.current is None
    assert picker.take() is None


def test_folder_chooser_cannot_be_exposed_to_nonlocal_origin(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        create_app(tmp_path, origin="https://example.com", host_checks=True, folder_picker=FolderPicker())


def test_container_dashboard_does_not_open_host_dialog(client, auth):
    assert client.post("/api/onboarding/choose-folder").status_code == 403
    assert client.post("/api/onboarding/choose-folder", headers=auth).status_code == 409
