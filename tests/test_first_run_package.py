import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_first_run_server import request

from stackarr.first_run_docker import SetupError
from stackarr.first_run_package import PackageStart, local_url
from stackarr.first_run_server import ReadinessServer
from stackarr.self_update import FILES


def make(tmp_path, runner):
    return PackageStart(tmp_path / "package", tmp_path / "docker", tmp_path / "connect", runner=runner)


def test_home_network_launcher_only_uses_saved_state_and_verified_package(tmp_path, monkeypatch):
    start = make(tmp_path, None)
    launched, verified = [], []
    with pytest.raises(SetupError, match="Set up Stackarr first"):
        start.network()
    start.state_root.mkdir()
    (start.state_root / "installation.json").write_text("{}")
    monkeypatch.setattr("stackarr.self_update.package", lambda path:verified.append(path))
    monkeypatch.setattr("stackarr.first_run_package.subprocess.Popen", lambda command, **options:launched.append((command,options)))
    assert start.network()["opened"]
    assert verified == [start.package_root]
    assert launched[0][0] == [str(start.package_root / "StackarrPreview.exe"),"--lan-setup",str(start.state_root)]
    assert launched[0][1]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert not (start.state_root / "stackarr-runtime.json").exists()


def report(mode="install", state="ready"):
    return {"mode": mode, "state": state}


def finish(start):
    start.worker.join(timeout=3)
    assert not start.worker.is_alive()
    return start.status()


@pytest.mark.parametrize("mode", ["install", "connect"])
def test_check_is_required_and_duplicate_continuation_does_not_launch_twice(tmp_path, mode):
    calls, release, entered = [], threading.Event(), threading.Event()
    def run(selected):
        calls.append(selected)
        entered.set()
        assert release.wait(3)
        return {"url": "http://127.0.0.1:29370/#private-setup"}
    start = make(tmp_path, run)
    with pytest.raises(SetupError):
        start.start(mode, report(mode, "attention"))
    assert not list(tmp_path.iterdir())
    start.start(mode, report(mode))
    assert entered.wait(3)
    assert start.start(mode, report(mode))["phase"] == "starting"
    release.set()
    assert finish(start)["phase"] == "ready" and calls == [mode]
    assert start.start(mode, report(mode))["phase"] == "ready" and calls == [mode]


@pytest.mark.parametrize("url", ["https://untrusted.invalid/", "http://untrusted.invalid/", "file:///data", "javascript:alert(1)",
                                "http://owner:password@localhost:28000/", "http://localhost:28000/?token=private", "http://localhost:28000/other"])
def test_only_fixed_loopback_dashboard_urls_are_accepted(tmp_path, url):
    start = make(tmp_path, lambda mode: {"url": url})
    start.start("install", report())
    result = finish(start)
    assert result["phase"] == "failed" and "url" not in result
    assert url not in json.dumps(result)
    with pytest.raises((SetupError, ValueError)):
        local_url(url)


def test_failed_launch_can_retry_without_replacing_saved_state(tmp_path):
    state = tmp_path / "docker"
    state.mkdir()
    sentinel = state / "keep-settings"
    sentinel.write_bytes(b"original")
    calls = []
    def run(mode):
        calls.append(mode)
        if len(calls) == 1:
            raise OSError("private local details")
        return {"url": "http://localhost:29370/"}
    start = make(tmp_path, run)
    start.start("install", report())
    assert finish(start)["phase"] == "failed"
    start.start("install", report())
    assert finish(start)["phase"] == "ready" and sentinel.read_bytes() == b"original"


@pytest.mark.parametrize("review", ["repair", "reinstall"])
def test_retained_runtime_review_is_opened_without_automatic_approval(tmp_path, review):
    start = make(tmp_path, lambda _: {"review": review})
    start.start("install", report())
    result = finish(start)
    assert result["phase"] == "review-required" and review in result["message"] and "url" not in result


def test_local_and_docker_state_cannot_overlap(tmp_path):
    for connect in (tmp_path / "docker", tmp_path, tmp_path / "docker/local"):
        with pytest.raises(SetupError):
            PackageStart(tmp_path / "package", tmp_path / "docker", connect)


def test_http_continuation_rechecks_readiness_and_rejects_browser_commands(tmp_path):
    calls, state = [], ["ready"]
    start = make(tmp_path, lambda mode: calls.append(mode) or {"url": "http://localhost:29370/"})
    setup = SimpleNamespace(status=lambda: {"busy": False}, worker=None)
    with ReadinessServer(lambda mode: report(mode, state[0]), setup, start) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            assert json.loads(request(server)[2])["integrated"]
            state[0] = "attention"
            assert request(server, path="/api/stackarr/start")[0] == 409 and not calls
            state[0] = "ready"
            assert request(server, path="/api/stackarr/start", body='{"mode":"install","command":"arbitrary"}')[0] == 400
            assert request(server, path="/api/stackarr/start", **{"Origin": "https://untrusted.invalid"})[0] == 403
            assert request(server, path="/api/stackarr/status", **{"X-Readiness-Key": "wrong"})[0] == 403
            setup.status = lambda: {"busy": True}
            assert request(server, path="/api/stackarr/start")[0] == 409 and not calls
            setup.status = lambda: {"busy": False}
            assert request(server, path="/api/stackarr/start", body='{"mode":"connect"}')[0] == 200
            assert finish(start)["mode"] == "connect" and calls == ["connect"]
        finally:
            server.shutdown()
            worker.join(timeout=3)


def release(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    for name in FILES:
        (root / name).write_bytes(("Synthetic " + name).encode())
    manifest = {"schema": 1, "release": "Stackarr-Test", "image": "stackarr:fixture", "image_id": "sha256:" + "a" * 64,
                "maintenance": {"protocol": 1, "state_schema": 1},
                "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


@pytest.mark.parametrize("mode", ["install", "connect"])
@pytest.mark.skipif(os.name != "nt", reason="Windows packaged process commands")
def test_package_handoff_uses_fixed_commands_and_checked_private_report(tmp_path, monkeypatch, mode):
    from stackarr import first_run_package

    package = release(tmp_path)
    calls = []
    def execute(args, **kwargs):
        calls.append(args)
        assert not kwargs.get("shell") and kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
        report_flag = "-ResultFile" if mode == "install" else "--launcher-ready-report"
        Path(args[args.index(report_flag) + 1]).write_text(json.dumps({"url": "http://localhost:29370/"}))
        return SimpleNamespace(returncode=0, poll=lambda: None)
    monkeypatch.setattr(first_run_package.subprocess, "run", execute)
    monkeypatch.setattr(first_run_package.subprocess, "Popen", execute)
    start = PackageStart(package, tmp_path / "docker", tmp_path / "connect")
    assert start.launch(mode)["url"] == "http://localhost:29370/"
    assert len(calls) == 1
    if mode == "install":
        assert calls[0][calls[0].index("-StateDirectory") + 1] == str(tmp_path / "docker")
        assert "-NoBrowser" in calls[0]
    else:
        assert calls[0][0] == str(package / "StackarrPreview.exe")
        assert "--no-browser" in calls[0] and str(tmp_path / "connect") in calls[0]


def test_changed_package_is_rejected_before_any_process_is_started(tmp_path, monkeypatch):
    from stackarr.deployment import DeploymentError

    package = release(tmp_path)
    (package / "Start-StackarrPreview.ps1").write_bytes(b"changed")
    monkeypatch.setattr("stackarr.first_run_package.subprocess.run", lambda *a, **k: pytest.fail("Unverified package executed"))
    start = PackageStart(package, tmp_path / "docker", tmp_path / "connect")
    with pytest.raises(DeploymentError):
        start.launch("install")
