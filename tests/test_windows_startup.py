import hashlib
import json

import pytest

from stackarr import windows_startup as startup
from stackarr.self_update import FILES, read, write


class Registry:
    def __init__(self):
        self.values = {"Other media app": "unchanged"}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


@pytest.fixture
def configured(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    for name in FILES:
        (package / name).write_bytes(("Synthetic payload " + name).encode())
    manifest = {"schema": 1, "release": "Stackarr-Test", "maintenance": {"protocol": 1, "state_schema": 1},
                "image": "stackarr:test", "image_id": "sha256:" + "a" * 64, "signin_startup": 1,
                "files": {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in FILES}}
    write(package / "manifest.json", manifest)
    root = tmp_path / "state"
    root.mkdir()
    write(root / "installation.json", {"owner": "stackarr-docker-preview-v1"})
    write(root / "stackarr-runtime.json", {"release": "b" * 64})
    registry = Registry()
    return startup.Registration(root, package / "StackarrPreview.exe", registry)


def test_opt_in_is_required_and_disable_preserves_other_apps(configured):
    reg = configured
    assert reg.status() == {"enabled": False, "conflict": False}
    assert reg.enable()["enabled"]
    assert reg.enable()["enabled"]
    assert reg.registry.values[reg.name] == reg.command
    assert reg.disable() == {"enabled": False, "conflict": False}
    assert reg.registry.values == {"Other media app": "unchanged"}
    assert reg.disable() == {"enabled": False, "conflict": False}


def test_foreign_or_changed_registration_is_never_overwritten(configured):
    reg = configured
    reg.registry.values[reg.name] = "foreign"
    for action in (reg.enable, reg.disable):
        with pytest.raises(startup.StartupError):
            action()
    assert reg.registry.values[reg.name] == "foreign"
    del reg.registry.values[reg.name]
    reg.enable()
    reg.registry.values[reg.name] = "changed externally"
    with pytest.raises(startup.StartupError):
        reg.disable()
    assert reg.registry.values[reg.name] == "changed externally"


def test_first_startup_review_uses_saved_ports_to_capture_existing_runtime(configured, monkeypatch):
    reg = configured
    (reg.root / "stackarr-runtime.json").unlink()
    write(reg.root / "installation.json", {"owner": "stackarr-docker-preview-v1", "port": 29370, "controller_port": 29371})
    calls = []
    def adopt(updates, **ports):
        calls.append(ports)
        assert updates.package_root == reg.executable.parent
        write(reg.root / "stackarr-runtime.json", {"release": "b" * 64})
    monkeypatch.setattr(startup.SelfUpdates, "adopt", adopt)
    assert reg.enable()["enabled"]
    assert calls == [{"port": 29370, "controller_port": 29371}]


@pytest.mark.parametrize("damage", ["missing-state", "foreign-state", "changed-exe", "old-package", "removed", "pending"])
def test_invalid_registration_does_not_create_startup(configured, damage):
    reg = configured
    if damage == "missing-state":
        (reg.root / "stackarr-runtime.json").unlink()
    elif damage == "foreign-state":
        write(reg.root / "installation.json", {"owner": "foreign"})
    elif damage == "changed-exe":
        reg.executable.write_bytes(b"changed")
    elif damage == "old-package":
        manifest = read(reg.executable.parent / "manifest.json")
        manifest.pop("signin_startup")
        write(reg.executable.parent / "manifest.json", manifest)
    elif damage == "removed":
        write(reg.root / "stackarr-removed.json", {})
    else:
        home = reg.root / "stackarr-maintenance"
        job = home / "jobs" / ("c" * 32)
        job.mkdir(parents=True)
        write(home / "active-job.json", {"id": "c" * 32})
        write(job / "job.json", {"phase": "needs-recovery"})
    with pytest.raises((ValueError, OSError)):
        reg.enable()
    assert reg.registry.values == {"Other media app": "unchanged"}


def run(reg, **kwargs):
    return startup.resume(reg.root, reg.executable, registry=reg.registry, **kwargs)


def test_waits_for_docker_and_starts_only_once(configured):
    reg = configured
    reg.enable()
    clock = [0]
    calls = []
    def sleep(seconds):
        clock[0] += seconds
    assert run(reg, ready=lambda: clock[0] >= 10, start=lambda: calls.append("start"),
               clock=lambda: clock[0], sleep=sleep) == 0
    assert calls == ["start"] and clock[0] == 10
    assert read(reg.root / "signin-status.json")["state"] == "started"


def test_timeout_never_starts_or_leaks_diagnostics(configured):
    reg = configured
    reg.enable()
    clock = [0]
    def sleep(seconds):
        clock[0] += seconds
    assert run(reg, ready=lambda: False, start=lambda: pytest.fail("must not start"),
               clock=lambda: clock[0], sleep=sleep, wait_seconds=12) == 1
    assert clock[0] == 12
    assert "Docker did not become ready" in read(reg.root / "signin-status.json")["message"]


@pytest.mark.parametrize("action", ["disabled", "removed", "changed", "unregistered"])
def test_rechecks_consent_after_docker_wait(configured, action):
    reg = configured
    reg.enable()
    def ready():
        if action == "disabled":
            reg.disable()
        elif action == "removed":
            write(reg.root / "stackarr-removed.json", {})
        elif action == "changed":
            reg.registry.values[reg.name] = "external"
        else:
            reg.registry.delete(reg.name)
        return True
    assert run(reg, ready=ready, start=lambda: pytest.fail("consent revoked")) == 0


def test_start_failure_is_not_retried_and_exception_details_stay_private(configured):
    reg = configured
    reg.enable()
    calls = []
    def fail():
        calls.append(1)
        raise RuntimeError("sensitive fixture information")
    assert run(reg, ready=lambda: True, start=fail) == 1
    assert calls == [1]
    assert "sensitive" not in (reg.root / "signin-status.json").read_text()


def test_changed_package_blocks_resume_even_if_registry_matches(configured):
    reg = configured
    reg.enable()
    reg.executable.write_bytes(b"tampered")
    assert run(reg, ready=lambda: pytest.fail("not contacted")) == 1


def test_simultaneous_manual_start_does_not_launch_another_controller(configured):
    reg = configured
    reg.enable()
    identity = hashlib.sha256(str(reg.root).casefold().encode()).hexdigest()[:20]
    with startup.operation_lock(reg.root.parent / (".stackarr-start-" + identity)):
        assert run(reg, ready=lambda: pytest.fail("manual startup owns the lock")) == 1


def test_registry_failure_restores_previous_intent(configured, monkeypatch):
    reg = configured
    reg.enable()
    previous = read(reg.receipt)
    reg.disable()
    previous = read(reg.receipt)
    def denied(*args):
        raise PermissionError("denied")
    monkeypatch.setattr(reg.registry, "set", denied)
    with pytest.raises(PermissionError):
        reg.enable()
    assert read(reg.receipt) == previous
    assert reg.registry.values == {"Other media app": "unchanged"}


def test_no_implicit_setup_or_registration(tmp_path):
    root = tmp_path / "absent"
    assert startup.resume(root, tmp_path / "StackarrPreview.exe", registry=Registry()) == 1
    assert not root.exists()


def test_foreign_state_is_never_given_a_startup_report(tmp_path):
    root = tmp_path / "foreign"
    root.mkdir()
    write(root / "installation.json", {"owner": "another app"})
    before = list(root.iterdir())
    assert startup.resume(root, tmp_path / "StackarrPreview.exe", registry=Registry()) == 1
    assert list(root.iterdir()) == before
    registration = startup.Registration(root, tmp_path / "StackarrPreview.exe", Registry())
    assert registration.disable() == {"enabled": False, "conflict": False}
    assert list(root.iterdir()) == before


def test_startup_report_contains_only_redacted_fields(configured):
    reg = configured
    reg.enable()
    assert run(reg, ready=lambda: True, start=lambda: None) == 0
    report = json.loads((reg.root / "signin-status.json").read_text())
    assert set(report) == {"state", "checked_at", "message"}
