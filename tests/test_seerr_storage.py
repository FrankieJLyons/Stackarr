from types import SimpleNamespace

import pytest

from stackarr.deployment import DeploymentError
from stackarr.seerr_storage import CLEAR, PROBE, prepare


@pytest.fixture
def storage(monkeypatch):
    calls, audit = [], []
    flags = {"running": True, "shared": False, "changed": False, "bad_marker": False, "full": False, "reads": 0}
    class Maintenance:
        def __init__(self, deployments):
            pass
        def container(self, *args):
            return {"Id": "a" * 64, "State": {"Running": flags["running"]}}
        def resources(self, *args):
            flags["reads"] += 1
            if flags["shared"]:
                raise DeploymentError("private shared volume")
            return {"volume": "changed" if flags["changed"] and flags["reads"] > 1 else "original"}
    def call(args):
        calls.append(args)
        if args[-1] == PROBE:
            if flags["full"]:
                raise DeploymentError("private disk output")
            return "verified\n"
        assert args[-1] == CLEAR
        if flags["bad_marker"]:
            raise DeploymentError("private image marker")
        return "ready\n"
    monkeypatch.setattr("stackarr.seerr_storage.AppMaintenance", Maintenance)
    service = SimpleNamespace(_call=call, store=SimpleNamespace(audit=lambda *value: audit.append(value)))
    return service, {"apps": ["seerr"], "context": {"name": "fixture"}}, calls, audit, flags


def test_only_owned_seerr_gets_a_private_durable_probe_and_guarded_marker_clear(storage):
    service, payload, calls, audit, flags = storage
    prepare(service, "b" * 32, payload)
    assert flags["reads"] == 2 and len(calls) == 2
    assert all(args[:6] == ["--context", "fixture", "exec", "a" * 64, "node", "-e"] for args in calls)
    assert audit == [("deployment.seerr-storage-verified", "b" * 32)]
    prepare(service, "b" * 32, payload)
    assert len(calls) == 4  # Repeated resume is safe when the marker is already absent.


def test_unselected_seerr_never_inspects_or_writes(storage):
    service, _, calls, audit, flags = storage
    prepare(service, "b" * 32, {"apps": ["plex"]})
    assert not calls and not audit and flags["reads"] == 0


@pytest.mark.parametrize("failure,expected_calls", [("shared", 0), ("changed", 1), ("full", 1), ("bad_marker", 2), ("running", 0)])
def test_unverified_storage_is_preserved_and_errors_are_redacted(storage, failure, expected_calls):
    service, payload, calls, audit, flags = storage
    flags[failure] = failure != "running"
    with pytest.raises(DeploymentError) as error:
        prepare(service, "b" * 32, payload)
    assert error.value.kind == "seerr-storage" and "private" not in str(error.value)
    assert len(calls) == expected_calls and not audit
