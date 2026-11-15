import pytest

from stackarr.store import Store


def test_checksums_retention_and_corruption(tmp_path):
    store = Store(tmp_path)
    for _ in range(3):
        name = store.backup(2)
    assert len(list((tmp_path / "backups").glob("*.json"))) == 2
    assert len(list((tmp_path / "backups").glob("*.sha256"))) == 2
    assert all(row["verified"] for row in store.backups())
    (tmp_path / "backups" / name).write_text("{}")
    assert not store.backups()[0]["verified"]
    with pytest.raises(ValueError, match="checksum"):
        store.backup_draft(name)


def test_backup_preview_cannot_apply_without_save(client, auth, app):
    before = app.state.store.config()
    name = client.post("/api/backup", headers=auth).json()["file"]
    assert client.get("/api/backups").json()[0]["verified"]
    response = client.post(f"/api/backups/{name}/preview", headers=auth)
    assert response.status_code == 200 and not response.json()["saved"]
    assert app.state.store.config() == before


def test_daily_schedule_survives_restart_and_failed_attempt(tmp_path):
    store = Store(tmp_path)
    assert store.claim_backup_schedule(now=100000)
    assert not Store(tmp_path).claim_backup_schedule(now=100001)
    assert Store(tmp_path).claim_backup_schedule(now=186400)


@pytest.mark.parametrize("name", ["../stackarr.db", "config-1.json/../../secrets.key", "secrets.key"])
def test_backup_names_cannot_escape_directory(tmp_path, name):
    with pytest.raises(ValueError):
        Store(tmp_path).backup_draft(name)
