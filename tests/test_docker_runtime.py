import json
import subprocess
from types import SimpleNamespace

import pytest

from stackarr import docker_runtime


@pytest.fixture
def host(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(docker_runtime.Path, "exists", lambda path: False)
    monkeypatch.setattr(docker_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(docker_runtime, "executable", lambda: "fixture-docker")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 8 and not kwargs.get("shell")
        if args[-1] == "show":
            value = "fixture"
        elif "inspect" in args:
            value = "npipe:////./pipe/fixture"
        elif "compose" in args:
            value = "5.5.1"
        else:
            value = json.dumps({"OSType": "linux", "Architecture": "x86_64"})
        return SimpleNamespace(returncode=0, stdout=value)

    return calls, run


def test_read_only_runtime_check_and_disabled_scope(host):
    calls, run = host
    assert docker_runtime.inspect(runner=run)["state"] == "not-checked"
    assert not calls
    result = docker_runtime.inspect(enabled=True, runner=run)
    assert result["state"] == "ready" and not result["installation_started"]
    assert len(calls) == 5
    assert all(not set(call) & {"up", "start", "run", "pull", "restart", "exec"} for call in calls)


def test_stopped_engine_is_actionable_and_redacted(host):
    calls, run = host

    def stopped(args, **kwargs):
        if "info" in args:
            return SimpleNamespace(returncode=1, stdout="private engine path", stderr="private password")
        return run(args, **kwargs)

    result = docker_runtime.inspect(enabled=True, runner=stopped)
    assert result["state"] == "needs-attention"
    assert "Open Docker Desktop" in result["checks"][-1]["detail"]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("endpoint", ["ssh://private-host", "tcp://private-host", "unix://relative", ""])
def test_remote_context_never_contacts_engine(host, endpoint):
    calls, run = host

    def remote(args, **kwargs):
        if "inspect" in args:
            return SimpleNamespace(returncode=0, stdout=endpoint)
        return run(args, **kwargs)

    result = docker_runtime.inspect(enabled=True, runner=remote)
    assert result["state"] == "needs-attention"
    assert not any("info" in call for call in calls)
    assert "private-host" not in json.dumps(result)


def test_timeout_and_malformed_engine_are_not_ready(host):
    _, run = host
    for stdout in ("not json", "[]", '{"OSType":"windows"}', '{"OSType":"linux","Architecture":null}'):
        def malformed(args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=stdout) if "info" in args else run(args, **kwargs)

        assert docker_runtime.inspect(enabled=True, runner=malformed)["state"] == "needs-attention"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private command", 8)

    assert "private command" not in json.dumps(docker_runtime.inspect(enabled=True, runner=timeout))


def test_windows_fallback_and_custom_command(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_runtime.shutil, "which", lambda command: None)
    monkeypatch.setattr(docker_runtime.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    candidate = tmp_path / "Programs/DockerDesktop/resources/bin/docker.exe"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("synthetic fixture, never executed")
    assert docker_runtime.executable() == str(candidate)
    assert docker_runtime.executable("nonexistent-docker") is None


def test_runtime_api_requires_auth_and_cannot_probe_container(client, auth, monkeypatch):
    monkeypatch.setattr(docker_runtime, "executable", lambda: pytest.fail("Container dashboard must not probe host"))
    assert client.post("/api/onboarding/runtime-check").status_code == 403
    result = client.post("/api/onboarding/runtime-check", headers=auth)
    assert result.status_code == 200 and result.json()["state"] == "not-checked"


def test_report_preserves_existing_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_runtime, "inspect", lambda **kwargs: {"state": "ready"})
    path = tmp_path / "report.json"
    assert docker_runtime.write_report(path) == 0
    with pytest.raises(FileExistsError):
        docker_runtime.write_report(path)
