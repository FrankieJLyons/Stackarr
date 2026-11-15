import json
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from stackarr.config import Config
from stackarr.installer import Installer, compose_plan, preflight


def configuration(tmp_path):
    config = Config().model_dump()
    config["storage"]["data_root"] = str(tmp_path)
    config["integrations"]["sonarr"].update(enabled=True, mode="install", port=18989)
    config["integrations"]["radarr"].update(enabled=True, mode="connect", url="https://remote.example")
    return Config.model_validate(config)


def test_mixed_plan_preserves_existing_and_has_no_host_privilege(tmp_path):
    plan = compose_plan(configuration(tmp_path))["compose"]
    assert set(plan["services"]) == {"sonarr"}
    service = plan["services"]["sonarr"]
    assert service["ports"][0]["host_ip"] == "127.0.0.1"
    assert "privileged" not in service
    assert "docker.sock" not in json.dumps(plan)
    assert service["volumes"][1]["bind"]["create_host_path"] is False


def test_qbittorrent_custom_port_matches_webui_and_internal_connections(tmp_path):
    from stackarr.wiring import address

    data = configuration(tmp_path).model_dump()
    data["integrations"]["qbittorrent"].update(enabled=True, mode="install", port=28080)
    config = Config.model_validate(data)
    service = compose_plan(config)["compose"]["services"]["qbittorrent"]
    assert service["ports"][0]["target"] == 28080
    assert service["ports"][0]["published"] == "28080"
    assert service["environment"]["WEBUI_PORT"] == "28080"
    assert address("qbittorrent", config.integrations["qbittorrent"]) == "http://qbittorrent:28080"


def test_owned_project_apply_resume_and_preserving_uninstall(tmp_path):
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    installer = Installer(tmp_path / "install", runner)
    config = configuration(tmp_path)
    installer.prepare(config)
    installer.run("apply")
    installer.run("apply")
    installer.run("stop")
    assert all("--project-name" in call for call in calls)
    assert calls[-1][-1] == "down"
    assert all("--volumes" not in call and "-v" not in call for call in calls)
    assert (tmp_path / "install" / "compose.json").exists()


def test_failure_records_resumable_state(tmp_path):
    def runner(args, **kwargs):
        return SimpleNamespace(returncode=0 if "config" in args else 1)

    installer = Installer(tmp_path / "install", runner)
    installer.prepare(configuration(tmp_path))
    with pytest.raises(ValueError, match="Compose failed"):
        installer.run("apply")
    assert json.loads((installer.directory / "stackarr-install.json").read_text())["stage"] == "apply-failed"


def test_refuse_existing_directory(tmp_path):
    (tmp_path / "existing.txt").write_text("preserve me")
    with pytest.raises(ValueError, match="empty"):
        Installer(tmp_path).prepare(configuration(tmp_path))
    assert (tmp_path / "existing.txt").read_text() == "preserve me"


def test_rollback_retains_previous_plan(tmp_path):
    installer = Installer(tmp_path / "install", lambda *a, **kw: SimpleNamespace(returncode=0))
    config = configuration(tmp_path)
    installer.prepare(config)
    original = (installer.directory / "compose.json").read_text()
    data = config.model_dump()
    data["integrations"]["sonarr"]["port"] = 18990
    installer.prepare(Config.model_validate(data))
    installer.run("rollback")
    assert (installer.directory / "compose.json").read_text() == original


def test_conflicting_port_and_missing_docker_are_actionable(tmp_path):
    config = configuration(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        config.integrations["sonarr"].port = sock.getsockname()[1]
        results = preflight(config, docker="stackarr-nonexistent-docker")
    assert not next(r for r in results if r["check"] == "docker")["ok"]
    assert not next(r for r in results if r["check"] == "sonarr port")["ok"]


def test_permission_failure(tmp_path):
    with patch("stackarr.installer.os.access", return_value=False):
        results = preflight(configuration(tmp_path), docker="stackarr-nonexistent-docker")
    assert not next(r for r in results if r["check"] == "permissions")["ok"]


def test_no_legacy_in_distribution_contract():
    assert "prune legacy" in Path("MANIFEST.in").read_text()
    assert "USER 10001:10001" in Path("Dockerfile").read_text()


def test_source_release_contract_excludes_legacy_runtime_and_secrets():
    source = Path("tools/package_release.py").read_text()
    assert '"outputs"' in source
    assert '".key"' in source
    assert '".pfx"' in source
    assert '"platform"' in source
    assert '"history-audit.json"' in source


def test_modified_plan_is_blocked_before_docker(tmp_path):
    calls = []
    installer = Installer(tmp_path / "install", lambda *a, **kw: calls.append(a))
    installer.prepare(configuration(tmp_path))
    path = installer.directory / "compose.json"
    changed = json.loads(path.read_text())
    changed["services"]["sonarr"]["privileged"] = True
    path.write_text(json.dumps(changed))
    for action in ("apply", "stop"):
        with pytest.raises(ValueError, match="plan changed"):
            installer.run(action)
    assert not calls
    with pytest.raises(ValueError, match="plan changed"):
        installer.prepare(configuration(tmp_path))


def test_prepare_checks_project_ownership_before_overwrite(tmp_path):
    installer = Installer(tmp_path / "install")
    config = configuration(tmp_path)
    installer.prepare(config)
    path = installer.directory / "stackarr-install.json"
    state = json.loads(path.read_text())
    state["project"] = "unrelated-project"
    path.write_text(json.dumps(state))
    before = (installer.directory / "compose.json").read_bytes()
    with pytest.raises(ValueError, match="ownership"):
        installer.prepare(config)
    assert (installer.directory / "compose.json").read_bytes() == before


def test_receipt_omits_webhook_and_records_plan_images(tmp_path):
    installer = Installer(tmp_path / "install")
    config = configuration(tmp_path)
    config.maintenance.notification_url = "https://example.test/private-webhook"
    installer.prepare(config)
    state = json.loads((installer.directory / "stackarr-install.json").read_text())
    assert "private-webhook" not in json.dumps(state)
    assert state["current"]["images"]["sonarr"]
