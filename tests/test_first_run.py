import json
import subprocess
from types import SimpleNamespace

import pytest

from stackarr import docker_runtime, first_run


@pytest.fixture
def facts():
    return {"windows": True, "architecture": "AMD64", "build": 26100, "workstation": True,
            "memory": 16 * 1024**3, "hypervisor": True, "virtualization": False}


def runtime(**_kwargs):
    return {"state": "ready", "checks": [{"check": "engine", "ok": True,
                                           "detail": "The local Linux x64 engine is running."}]}


def report(facts, **kwargs):
    return first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: 30 * 1024**3,
                             runtime_reader=runtime, **kwargs)


def row(result, key):
    return next(value for value in result["checks"] if value["id"] == key)


def test_ready_is_only_prerequisites(facts):
    result = report(facts)
    assert result["state"] == "ready"
    assert result["scope"] == "prerequisites-only" and not result["installation_started"]
    assert "startup after reboot" in result["next_step"]


def test_connect_does_not_probe_host_or_docker():
    def forbidden(**kwargs):
        pytest.fail("Existing-app choices must not inspect this host")

    result = first_run.inspect("connect", facts_reader=forbidden, space_reader=forbidden,
                               runtime_reader=forbidden)
    assert result["state"] == "ready" and len(result["checks"]) == 1
    assert "addresses and logins" in result["next_step"]
    with pytest.raises(ValueError):
        first_run.inspect("other", facts_reader=forbidden)


@pytest.mark.parametrize("changes,check", [
    ({"build": 22000}, "windows"), ({"workstation": False}, "windows"),
    ({"memory": 4 * 1024**3}, "memory"), ({"memory": True}, "memory"),
    ({"build": None}, "windows"), ({"workstation": None}, "windows"),
])
def test_unsupported_and_unknown_facts_do_not_pass(facts, changes, check):
    facts.update(changes)
    result = report(facts)
    assert result["state"] == "attention"
    assert row(result, check)["state"] in ("block", "unknown")


@pytest.mark.parametrize("changes", [{"windows": False}, {"architecture": "ARM64"},
                                     {"architecture": "x86"}, {"architecture": ""}])
def test_wrong_host_does_not_contact_docker(facts, changes):
    facts.update(changes)
    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: None,
                               runtime_reader=lambda **_: pytest.fail("Must not contact Docker"))
    assert result["state"] == "attention" and row(result, "runtime")["state"] == "skip"


def test_hypervisor_can_hide_firmware_flag_and_space_is_separately_scoped(facts):
    facts.update(virtualization=False, hypervisor=False, memory=8_000_000_000)
    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: 1024**3,
                               runtime_reader=runtime)
    assert result["state"] == "ready"
    assert row(result, "virtualization")["state"] == "pass"
    assert row(result, "space")["state"] == "note"
    assert "separate space checks" in row(result, "space")["detail"]


def test_unknown_virtualization_without_running_engine_needs_review(facts):
    facts.update(virtualization=False, hypervisor=False)
    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: None,
                               runtime_reader=lambda **_: {"state": "needs-attention", "checks": [
                                   {"check": "docker", "ok": False, "detail": "Install Docker using the official guide."}]})
    assert row(result, "virtualization")["state"] == "unknown"
    assert row(result, "runtime-docker")["action"]["url"] == first_run.DOCKER_GUIDE
    assert result["state"] == "attention"


def test_runtime_failure_does_not_expose_exception(facts):
    def failed(**_):
        raise OSError("sensitive local endpoint and credential")

    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: None, runtime_reader=failed)
    assert result["state"] == "attention" and "sensitive" not in json.dumps(result)


@pytest.mark.parametrize("scenario", ["missing", "stopped", "remote", "windows", "ready"])
def test_real_runtime_adapter_preserves_read_only_and_local_boundaries(facts, monkeypatch, scenario):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(docker_runtime.Path, "exists", lambda _: False)
    monkeypatch.setattr(docker_runtime.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(docker_runtime, "executable", lambda: None if scenario == "missing" else "fixture-docker")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 8 and not kwargs.get("shell")
        if args[-1] == "show":
            output = "fixture"
        elif "context" in args and "inspect" in args:
            output = "ssh://redacted-remote" if scenario == "remote" else "npipe:////./pipe/fixture"
        elif "compose" in args:
            output = "5.5.1"
        elif args[-1] == "{{json .DefaultAddressPools}}":
            output = "null"
        elif "network" in args:
            return SimpleNamespace(returncode=1, stdout="", stderr="redacted network data")
        else:
            if scenario == "stopped":
                raise subprocess.TimeoutExpired("sensitive endpoint", 8)
            output = json.dumps({"OSType": "windows" if scenario == "windows" else "linux", "Architecture": "x86_64"})
        return SimpleNamespace(returncode=0, stdout=output)

    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: None,
                               runtime_reader=lambda **kwargs: docker_runtime.inspect(runner=run, **kwargs))
    assert (result["state"] == "ready") == (scenario == "ready")
    if scenario in ("missing", "remote"):
        assert not any("info" in call for call in calls)
    if scenario == "missing":
        assert result["title"] == "Install Docker Desktop to continue"
        assert result["primary_action"]["label"] == "Get Docker Desktop"
    assert not any(set(call) & {"pull", "up", "start", "run", "prune", "exec", "stop"} for call in calls)
    assert "sensitive" not in json.dumps(result) and "redacted-remote" not in json.dumps(result)


def test_inventory_is_bounded_and_retains_only_allowlisted_facts(monkeypatch, tmp_path):
    monkeypatch.setattr(first_run.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "ARM64")

    def run(args, **kwargs):
        assert args[0] == str(tmp_path / "System32/WindowsPowerShell/v1.0/powershell.exe")
        assert args[1:4] == ["-NoProfile", "-NonInteractive", "-Command"]
        assert kwargs["timeout"] == 12 and not kwargs.get("shell")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"build": 26100, "memory": 16000000000,
                               "workstation": True, "hypervisor": True, "virtualization": False,
                               "hostname": "sensitive-host", "account": "sensitive-account"}))

    result = first_run.windows_facts(runner=run)
    assert result["architecture"] == "ARM64" and result["build"] == 26100
    assert "sensitive" not in json.dumps(result)


@pytest.mark.parametrize("output", ["bad-json", "[]", "x" * 4097,
                                    '{"build":true,"memory":"unknown","hypervisor":1}'])
def test_inventory_failure_stays_unknown(monkeypatch, tmp_path, output):
    monkeypatch.setattr(first_run.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    result = first_run.windows_facts(runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout=output))
    assert "build" not in result and "memory" not in result and "hypervisor" not in result


def test_inventory_timeout_and_non_windows_are_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(first_run.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemRoot", str(tmp_path))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("sensitive path", 12)

    assert "sensitive" not in json.dumps(first_run.windows_facts(runner=timeout))
    monkeypatch.setattr(first_run.platform, "system", lambda: "Linux")
    assert first_run.windows_facts(runner=lambda *_: pytest.fail("Wrong host")) == {"windows": False}


def test_space_is_read_only_and_does_not_return_path(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    before = list(tmp_path.iterdir())
    assert first_run.setup_space() >= 0 and list(tmp_path.iterdir()) == before
    monkeypatch.setenv("LOCALAPPDATA", "relative")
    assert first_run.setup_space() is None


def test_network_notes_do_not_become_green_checks(facts):
    result = first_run.inspect(facts_reader=lambda: facts, space_reader=lambda: None,
                               runtime_reader=lambda **_: {"state": "ready", "network_capacity": {"state": "low"},
                                                           "checks": [{"check": "network capacity", "ok": True,
                                                                       "detail": "Capacity is low."}]})
    assert row(result, "runtime-network-capacity")["state"] == "note"


def test_cli_report_is_new_observation_only(monkeypatch, tmp_path):
    import sys

    from stackarr import first_run_server

    path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["readiness", "--report", str(path), "--mode", "connect"])
    assert first_run_server.main() == 0
    before = path.read_bytes()
    assert first_run_server.main() == 2 and path.read_bytes() == before
