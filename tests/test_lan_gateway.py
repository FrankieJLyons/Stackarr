import json

import pytest

from stackarr.lan_gateway import gateway_config, resume


def test_gateway_restricts_bind_clients_routes_and_certificate_trust():
    config = gateway_config("https://stackarr.home.arpa:29443", "172.20.50.10", ["172.20.50.0/24"], 29123,
                            {"plex": {"origin": "https://plex.home.arpa:29443", "port": 32400}})
    assert "admin off" in config and "skip_install_trust" in config
    assert "disable_redirects" in config and "bind 172.20.50.10" in config
    assert "remote_ip 172.20.50.0/24" in config
    assert "reverse_proxy 127.0.0.1:29123" in config
    assert "reverse_proxy 127.0.0.1:32400" in config
    assert "tls_insecure" not in config and "0.0.0.0" not in config
    assert 'respond "Host not allowed." 421' in config


@pytest.mark.parametrize("change", [
    {"bind": "0.0.0.0"}, {"bind": "8.8.8.8"}, {"bind": "127.0.0.1"},
    {"clients": ["0.0.0.0/0"]}, {"clients": ["10.0.0.0/8"]}, {"clients": []},
    {"clients": ["172.20.50.1/24"]}, {"origin": "https://server.home.arpa\nreverse_proxy attacker"},
    {"dashboard_port": 29443}, {"dashboard_port": True},
    {"apps": {"plex": {"origin": "https://plex.home.arpa", "port": 1234, "token": "secret"}}},
])
def test_gateway_rejects_exposure_and_configuration_injection(change):
    args = dict(origin="https://stackarr.home.arpa:29443", bind="172.20.50.10", clients=["172.20.50.0/24"], dashboard_port=29123)
    with pytest.raises((ValueError, KeyError)):
        gateway_config(**(args | change))


def test_delayed_runtime_retries_only_dependencies_and_starts_once(tmp_path, monkeypatch):
    monkeypatch.setattr("stackarr.lan_gateway.verified", lambda p: (tmp_path, {"request": {"state_root": str(tmp_path / "state")}}))
    checks = iter([{"state": "needs-attention"}, {"state": "needs-attention"}, {"state": "ready"}])
    waits, starts = [], []
    assert resume(tmp_path, readiness=lambda: next(checks), start=lambda: starts.append(1) or "local", sleep=waits.append) == "local"
    assert waits == [2, 4] and starts == [1]
    assert json.loads((tmp_path / "startup-status.json").read_text())["signed_out_boot"] == "not-certified"


def test_unavailable_runtime_and_rejected_start_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("stackarr.lan_gateway.verified", lambda p: (tmp_path, {"request": {"state_root": str(tmp_path / "state")}}))
    waits = []
    with pytest.raises(ValueError, match="did not become ready"):
        resume(tmp_path, readiness=lambda: {"state": "needs-attention"}, start=lambda: pytest.fail("Must not start"), sleep=waits.append)
    assert waits == [2, 4, 8, 16, 30]
    def fail():
        raise ValueError("Changed ownership")
    with pytest.raises(ValueError, match="Changed ownership"):
        resume(tmp_path, readiness=lambda: {"state": "ready"}, start=fail, sleep=lambda _: pytest.fail("No retry"))
    assert json.loads((tmp_path / "startup-status.json").read_text())["reason"] == "runtime-start-rejected"
