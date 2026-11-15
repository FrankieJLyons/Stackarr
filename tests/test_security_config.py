import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from stackarr.config import Config
from stackarr.server import create_app
from stackarr.store import Conflict, Store


def test_first_run_requires_local_token_and_password(client):
    assert client.get("/api/session").json()["setup_required"]
    assert client.get("/api/config").status_code == 401
    assert (
        client.post(
            "/api/setup",
            json={"password": "a long test password", "setup_token": "wrong"},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 403
    )


def test_sessions_csrf_origin_host_and_logout(client, auth):
    assert client.get("/api/config").status_code == 200
    assert client.post("/api/backup").status_code == 403
    assert client.post("/api/backup", headers={"Origin": "http://testserver"}).status_code == 403
    assert client.post("/api/backup", headers=auth | {"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/healthz", headers={"Host": "evil.example"}).status_code == 400
    response = client.get("/api/status")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.post("/api/logout", headers=auth).status_code == 200
    assert client.get("/api/config").status_code == 401


def test_settings_secrets_redaction_concurrency_and_restart(client, app, auth):
    payload = client.get("/api/config").json()
    config = payload["config"]
    config["integrations"]["sonarr"].update(enabled=True, url="https://sonarr.example")
    secret = "synthetic-secret-not-a-real-key"
    update = {
        "revision": payload["revision"],
        "config": config,
        "credentials": {"sonarr": {"api_key": secret}},
    }
    assert client.put("/api/config", json=update, headers=auth).status_code == 200
    assert client.put("/api/config", json=update, headers=auth).status_code == 409
    assert app.state.store.secret("sonarr")["api_key"] == secret
    assert secret.encode() not in app.state.store.path.read_bytes()
    for path in ("config", "export", "support", "audit"):
        assert secret not in client.get("/api/" + path).text
    restarted = create_app(app.state.store.root, origin="http://testserver", background=False)
    assert restarted.state.store.config()[1].integrations["sonarr"].enabled
    assert restarted.state.store.secret("sonarr")["api_key"] == secret
    assert restarted.state.collector.view()["integrations"][0]["state"] == "pending"


def test_password_errors_do_not_echo_values(client):
    response = client.post("/api/login", json={"password": "secret"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 422
    assert '"input"' not in response.text
    assert "secret" not in response.text


def test_backup_retention_and_restore_validation(client, auth, app):
    for _ in range(4):
        app.state.store.backup(2)
    files = list((app.state.store.root / "backups").glob("*.json"))
    assert len(files) == 2
    restored = Config.model_validate_json(files[0].read_text())
    assert restored.version == 3
    assert "credentials" not in json.loads(files[0].read_text())


@pytest.mark.parametrize(
    "edit",
    [
        lambda c: c.update(version=99),
        lambda c: c["integrations"]["sonarr"].update(enabled=True, url="file:///etc/passwd"),
        lambda c: c["integrations"]["sonarr"].update(enabled=True, url="http://user:password@example.com"),
        lambda c: c["maintenance"].update(delete_downloads=True),
        lambda c: c["maintenance"].update(recovery_enabled=True),
        lambda c: c["maintenance"]["storage_guard"].update(enabled=True),
        lambda c: c["maintenance"]["storage_guard"].update(monitored_path="/data", pause_below_gb=100, resume_at_gb=50),
        lambda c: c["dashboard"].update(refresh_seconds=0),
        lambda c: c["integrations"].pop("sonarr"),
        lambda c: c["integrations"]["sonarr"].update(enabled=True, mode="install", port=8787),
    ],
)
def test_validation(edit):
    config = Config().model_dump()
    edit(config)
    with pytest.raises(ValidationError):
        Config.model_validate(config)


def test_parallel_updates_are_atomic(tmp_path):
    store = Store(tmp_path)

    def write(_):
        try:
            store.save(Config(), 1)
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(write, range(8)))
    assert sum(outcomes) == 1
    assert store.config()[0] == 2


def test_no_secrets_commit_on_failed_config_write(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(Conflict):
        store.save(Config(), 0, {"sonarr": {"api_key": "synthetic"}})
    assert store.secret("sonarr") == {}


def test_login_rate_limit(client):
    for _ in range(10):
        client.post(
            "/api/login",
            json={"password": "incorrect test password"},
            headers={"Origin": "http://testserver"},
        )
    assert (
        client.post(
            "/api/login",
            json={"password": "incorrect test password"},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 429
    )
