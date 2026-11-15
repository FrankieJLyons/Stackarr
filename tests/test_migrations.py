import json

import pytest

from stackarr.config import Config
from stackarr.store import Store


def test_upgrade_encrypts_legacy_webhook_once(tmp_path):
    store = Store(tmp_path)
    legacy = Config().model_dump()
    legacy["version"] = 1
    legacy["maintenance"].update(notification_url="https://example.test/private-token", notifications_enabled=True)
    with store.db() as db:
        db.execute("UPDATE settings SET data=?", (json.dumps(legacy),))
    upgraded = Store(tmp_path)
    revision, config = upgraded.config()
    assert revision == 2 and config.version == 3
    assert config.maintenance.notification_url == ""
    assert upgraded.secret("notification")["url"].endswith("private-token")
    assert b"private-token" not in upgraded.path.read_bytes()
    assert Store(tmp_path).config()[0] == revision


def test_future_version_is_not_overwritten(tmp_path):
    store = Store(tmp_path)
    data = Config().model_dump() | {"version": 99}
    with store.db() as db:
        db.execute("UPDATE settings SET data=?", (json.dumps(data),))
    with pytest.raises(ValueError):
        Store(tmp_path)
    with store.db() as db:
        assert json.loads(db.execute("SELECT data FROM settings").fetchone()[0])["version"] == 99


def test_webhook_survives_unrelated_save_and_never_leaks(client, auth, app):
    original = client.get("/api/config").json()
    config = original["config"]
    secret = "https://example.test/synthetic-private-token"
    config["maintenance"].update(notification_url=secret, notifications_enabled=True)
    assert client.put("/api/config", headers=auth, json={"revision": original["revision"], "config": config}).status_code == 200
    saved = client.get("/api/config").json()
    assert saved["notification_configured"]
    assert client.put("/api/config", headers=auth, json={"revision": saved["revision"], "config": saved["config"]}).status_code == 200
    assert app.state.store.secret("notification")["url"] == secret
    assert secret.encode() not in app.state.store.path.read_bytes()
    for endpoint in ("config", "export", "support", "audit", "plan"):
        assert secret not in client.get("/api/" + endpoint).text


def test_import_validation_is_a_redacted_draft(client, auth, app):
    original = app.state.store.config()
    legacy = Config().model_dump() | {"version": 1}
    legacy["maintenance"]["notification_url"] = "https://example.test/private-token"
    response = client.post("/api/config/validate", headers=auth, json={"config": legacy})
    assert response.status_code == 200
    assert response.json()["config"]["version"] == 3
    assert "private-token" not in response.text
    assert app.state.store.config() == original
    assert app.state.store.secret("notification") == {}
