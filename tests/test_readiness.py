import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from stackarr.config import Config
from stackarr.installer import preflight
from stackarr.readiness import report


def test_disabled_does_not_probe_host():
    with patch("stackarr.readiness.preflight") as probe:
        assert not report(Config())["preflight_passed"]
        probe.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ssh://example", "tcp://example:2375", "", "unix://relative"])
def test_remote_or_invalid_context_does_not_probe_local_storage(endpoint):
    with patch("stackarr.readiness.Path.exists", return_value=False), patch.dict("os.environ", {}, clear=True), patch("stackarr.readiness.docker_executable", return_value="docker"), patch("stackarr.readiness.preflight") as probe:
        result = report(Config(), enabled=True, runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout=endpoint))
        assert not result["preflight_passed"]
        assert endpoint not in str(result) or not endpoint
        probe.assert_not_called()


def test_container_cannot_pass_host_check():
    with patch("stackarr.readiness.Path.exists", return_value=True), patch("stackarr.readiness.preflight") as probe:
        assert report(Config(), enabled=True)["scope"] == "unverified"
        probe.assert_not_called()


def test_local_report_is_scoped_and_has_config_identity():
    with patch("stackarr.readiness.Path.exists", return_value=False), patch.dict("os.environ", {}, clear=True), patch("stackarr.readiness.docker_executable", return_value="docker"), patch("stackarr.readiness.preflight", return_value=[{"check": "fixture", "ok": True, "detail": "synthetic"}]):
        result = report(Config(), enabled=True, runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="unix:///var/run/docker.sock"))
        assert result["preflight_passed"]
        assert not result["installation_started"]
        assert len(result["configuration"]) == 64


def test_context_timeout_is_redacted():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("synthetic-private-command", 10)
    with patch("stackarr.readiness.Path.exists", return_value=False), patch.dict("os.environ", {}, clear=True), patch("stackarr.readiness.docker_executable", return_value="docker"):
        result = report(Config(), enabled=True, runner=timeout)
        assert not result["preflight_passed"]
        assert "synthetic-private-command" not in str(result)


def test_web_host_check_is_disabled_by_default(client, auth):
    client.put("/api/onboarding", json={"revision": 1, "draft": {"apps": ["kuma"]}}, headers=auth)
    assert client.post("/api/onboarding/host-check").status_code == 403
    response = client.post("/api/onboarding/host-check", headers=auth)
    assert response.status_code == 200
    assert not response.json()["preflight_passed"]
    assert response.json()["scope"] == "unverified"


@pytest.mark.parametrize("version,accepted", [("1.29.2", False), ("v2.39.1", True), ("2.40.0", True), ("5.5.1", True), ("v5.5.1", True), ("2.garbage", False), ("6.0.0", False), ("unexpected", False)])
def test_preflight_requires_supported_compose(version, accepted):
    def run(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=version if "compose" in args else "linux")
    with patch("stackarr.installer.shutil.which", return_value="docker"), patch("stackarr.installer.subprocess.run", side_effect=run):
        checks = preflight(Config(), check_ports=False)
        assert next(c for c in checks if c["check"] == "compose")["ok"] is accepted


@pytest.mark.parametrize("enabled", [False, True])
def test_connection_only_needs_no_docker_or_host_access(enabled):
    config = Config()
    config.integrations["plex"].enabled = True
    config.integrations["plex"].url = "http://existing.example"
    with patch("stackarr.readiness.preflight") as probe, patch("stackarr.readiness.docker_executable") as find:
        result = report(config, enabled=enabled)
        assert result["preflight_passed"] and result["scope"] == "connection-only"
        assert not result["installation_started"]
        probe.assert_not_called()
        find.assert_not_called()


def test_mixed_plan_still_requires_installation_host_checks():
    config = Config()
    config.integrations["plex"].enabled = True
    config.integrations["plex"].url = "http://existing.example"
    config.integrations["seerr"].enabled = True
    config.integrations["seerr"].mode = "install"
    assert not report(config)["preflight_passed"]


def test_connect_only_web_wizard_does_not_report_optional_docker_as_failure(client, auth):
    client.put("/api/onboarding", json={"revision": 1, "draft": {"apps": ["plex"], "choices": {"plex": {"mode": "connect", "url": "http://existing.example"}}}}, headers=auth)
    response = client.post("/api/onboarding/host-check", headers=auth)
    assert response.status_code == 200
    assert response.json()["scope"] == "connection-only"
    assert all(row["ok"] for row in response.json()["checks"])
