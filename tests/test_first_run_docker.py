import contextlib
import hashlib
import io
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from stackarr import first_run_docker as setup

PAYLOAD = b"Synthetic installer fixture, never executed"


def eligible():
    return {"mode": "install", "primary_action": {"label": "Get Docker Desktop"},
            "checks": [{"id": key, "state": "pass"} for key in ("windows", "architecture", "memory")]}


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setitem(setup.RELEASE, "sha256", hashlib.sha256(PAYLOAD).hexdigest())
    monkeypatch.setitem(setup.RELEASE, "bytes", len(PAYLOAD))
    events = []

    def download(path, update, cancelled):
        events.append("download")
        path.write_bytes(PAYLOAD)
        update(len(PAYLOAD))
        return True

    def sign(path):
        assert path.read_bytes() == PAYLOAD
        events.append("signature")

    def launch(path):
        assert events[-1] == "signature" and path.read_bytes() == PAYLOAD
        events.append("installer")
        return 0

    instance = setup.DockerSetup(tmp_path / "setup", exists=lambda: False, downloader=download,
                                 signer=sign, launcher=launch, locker=lambda _: contextlib.nullcontext())
    return instance, events


def run(instance, **kwargs):
    review = instance.review(eligible())
    instance.start(review["review_id"], eligible(), **kwargs)
    instance.worker.join(timeout=5)
    assert not instance.worker.is_alive()
    return instance.status()


def test_explicit_review_verification_and_install_order(service):
    instance, events = service
    review = instance.review(eligible())
    assert not events and not instance.home().exists()
    assert review["version"] == "4.95.0" and "terms" in review
    instance.start(review["review_id"], eligible())
    instance.worker.join(timeout=5)
    assert instance.status()["phase"] == "complete"
    assert events == ["download", "signature", "installer"]
    assert not list(instance.home().glob("*.exe"))
    with pytest.raises(setup.SetupError):
        instance.start(review["review_id"], eligible())


@pytest.mark.parametrize("key", ["windows", "architecture", "memory"])
def test_host_requirements_are_rechecked_before_review(service, key):
    instance, events = service
    report = eligible()
    next(row for row in report["checks"] if row["id"] == key)["state"] = "unknown"
    with pytest.raises(setup.SetupError):
        instance.review(report)
    assert not events


def test_existing_docker_or_changed_choice_cannot_be_reinstalled(service):
    instance, events = service
    review = instance.review(eligible())
    instance.exists = lambda: True
    with pytest.raises(setup.SetupError):
        instance.start(review["review_id"], eligible())
    instance.exists = lambda: False
    report = eligible()
    report["mode"] = "connect"
    with pytest.raises(setup.SetupError):
        instance.review(report)
    assert not events


def test_changed_installation_after_download_prevents_launch(service):
    instance, events = service
    previous = instance.downloader
    state = [False]
    instance.exists = lambda: state[0]

    def download(*args):
        result = previous(*args)
        state[0] = True
        return result

    instance.downloader = download
    assert run(instance)["phase"] == "already-installed" and "installer" not in events


def test_review_expiry_and_unknown_review(service, monkeypatch):
    instance, events = service
    review = instance.review(eligible())
    instance.reviewed = (review["review_id"], -1, False)
    with pytest.raises(setup.SetupError):
        instance.start(review["review_id"], eligible())
    with pytest.raises(setup.SetupError):
        instance.start("unknown", eligible())
    assert not events


@pytest.mark.parametrize("failure", ["checksum", "signature"])
def test_bad_payload_is_never_executed(service, failure):
    instance, events = service
    if failure == "checksum":
        def corrupted(path, update, cancelled):
            path.write_bytes(b"corrupted")
            return True
        instance.downloader = corrupted
    else:
        def bad_signature(path):
            raise ValueError("private certificate diagnostic")
        instance.signer = bad_signature
    status = run(instance)
    assert status["phase"] == "verification-failed" and "installer" not in events
    assert "private" not in json.dumps(status)


@pytest.mark.parametrize("code,phase", [(0, "complete"), (3010, "restart-needed"), (1, "failed"), (1223, "failed")])
def test_installer_outcomes_are_explicit(service, code, phase):
    instance, _ = service
    instance.launcher = lambda path: code
    assert run(instance)["phase"] == phase


def test_cancel_download_never_launches_installer(service):
    instance, events = service
    entered = threading.Event()

    def downloading(path, update, cancelled):
        path.write_bytes(b"partial")
        entered.set()
        assert cancelled.wait(3)
        return False

    instance.downloader = downloading
    review = instance.review(eligible())
    instance.start(review["review_id"], eligible())
    assert entered.wait(3) and instance.status()["busy"]
    assert instance.cancel()["cancelling"]
    instance.worker.join(timeout=5)
    assert instance.status()["phase"] == "cancelled" and "installer" not in events
    assert not list(instance.home().glob("*.exe"))


def test_second_window_observes_busy_and_cannot_start_again(service):
    instance, _ = service
    entered, release = threading.Event(), threading.Event()
    previous = instance.downloader

    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return previous(*args)

    instance.downloader = blocked
    review = instance.review(eligible())
    instance.start(review["review_id"], eligible())
    try:
        assert entered.wait(3)
        other = setup.DockerSetup(instance.home(), exists=lambda: False)
        assert other.status()["busy"]
        with pytest.raises(setup.SetupError):
            other.review(eligible())
    finally:
        release.set()
        instance.worker.join(timeout=5)


def test_interruption_does_not_relaunch_and_requires_acknowledgement(service):
    instance, events = service
    instance.save("installing")
    assert instance.status()["phase"] == "interrupted" and not events
    review = instance.review(eligible())
    assert review["previous_installer_check"]
    with pytest.raises(setup.SetupError):
        instance.start(review["review_id"], eligible())
    instance.start(review["review_id"], eligible(), previous_closed=True)
    instance.worker.join(timeout=5)
    assert instance.status()["phase"] == "complete"


def test_installer_arguments_leave_terms_and_restarts_to_user(monkeypatch, tmp_path):
    calls = []

    def popen(args, **kwargs):
        calls.append(args)
        assert not kwargs.get("shell")
        return SimpleNamespace(wait=lambda: 3010)

    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    monkeypatch.setattr(setup.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    path = tmp_path / "installer.exe"
    assert setup.launch(path) == 3010
    assert calls == [[str(path), "install", "--user"]]


@pytest.mark.parametrize("url", ["http://desktop.docker.com/file", "https://untrusted.invalid/file", "file:///installer"])
def test_download_cannot_redirect_outside_official_https(url):
    with pytest.raises(setup.SetupError):
        setup.DockerRedirects().redirect_request(None, None, 302, "redirect", {}, url)


def test_download_is_size_bounded_and_exclusive(service, monkeypatch, tmp_path):
    path = tmp_path / "download.exe"

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(PAYLOAD))}

    monkeypatch.setattr(setup.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=lambda *a, **k: Response(PAYLOAD)))
    values = []
    assert setup.download(path, values.append, threading.Event())
    assert path.read_bytes() == PAYLOAD and values[-1] == len(PAYLOAD)
    with pytest.raises(FileExistsError):
        setup.download(path, values.append, threading.Event())
    monkeypatch.setitem(setup.RELEASE, "bytes", 1)
    with pytest.raises(setup.SetupError):
        setup.download(tmp_path / "oversized.exe", values.append, threading.Event())


def test_journal_does_not_echo_untrusted_content(service):
    instance, _ = service
    instance.home().mkdir()
    (instance.home() / "job.json").write_text('{"phase":"untrusted private value"}')
    with pytest.raises(setup.SetupError, match="Saved Docker setup"):
        instance.status()
    instance.root = Path("relative")
    with pytest.raises(setup.SetupError):
        instance.home()


def test_temporary_windows_journal_sharing_denial_retries_safely(service, monkeypatch):
    instance, _ = service
    replace = setup.os.replace
    calls = []

    def busy(source, destination):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("synthetic brief sharing denial")
        return replace(source, destination)

    monkeypatch.setattr(setup.os, "replace", busy)
    instance.save("complete")
    assert len(calls) == 3 and instance.status()["phase"] == "complete"


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing and Authenticode semantics")
def test_payload_lock_prevents_replacement(tmp_path):
    path = tmp_path / "locked.exe"
    path.write_bytes(PAYLOAD)
    with setup.payload_lock(path):
        with pytest.raises(OSError):
            path.write_bytes(b"replacement")
        assert path.read_bytes() == PAYLOAD


@pytest.mark.skipif(os.name != "nt", reason="Windows Authenticode subprocess")
@pytest.mark.parametrize("signature,passed", [
    ({"status": "Valid", "subject": "CN=Docker Inc, O=Docker Inc, C=US"}, True),
    ({"status": "NotSigned", "subject": "O=Docker Inc"}, False),
    ({"status": "Valid", "subject": "O=Untrusted Docker Inc"}, False),
])
def test_signature_status_publisher_and_windows_module_scope(tmp_path, signature, passed):
    def runner(args, **kwargs):
        assert "Microsoft" not in args[-1]  # The command uses the built-in signature cmdlet.
        assert Path(kwargs["env"]["PSModulePath"]).as_posix().endswith("WindowsPowerShell/v1.0/Modules")
        assert kwargs["timeout"] == 60 and not kwargs.get("shell")
        return SimpleNamespace(returncode=0, stdout=json.dumps(signature))

    if passed:
        setup.verify_signature(tmp_path / "payload.exe", runner=runner)
    else:
        with pytest.raises(setup.SetupError):
            setup.verify_signature(tmp_path / "payload.exe", runner=runner)


def test_native_errors_do_not_escape_to_status(service):
    instance, _ = service

    def failed(*args):
        raise subprocess.SubprocessError("private local path")

    instance.launcher = failed
    result = run(instance)
    assert result["phase"] == "failed" and "private" not in json.dumps(result)
