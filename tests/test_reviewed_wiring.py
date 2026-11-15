import pytest


@pytest.fixture
def wiring_calls(monkeypatch, app):
    calls = []

    async def build(store, transport):
        calls.append("preview")
        return {"revision": store.config()[0], "changes": [], "notices": []}

    async def apply(store, plan, transport):
        calls.append("apply")
        return []

    monkeypatch.setattr("stackarr.wiring.build_plan", build)
    monkeypatch.setattr("stackarr.wiring.apply_plan", apply)
    return calls


def test_apply_requires_review_and_does_not_rebuild(client, auth, wiring_calls):
    assert client.post("/api/wiring/apply", headers=auth, json={"review_token": "x" * 32}).status_code == 409
    preview = client.get("/api/wiring/preview").json()
    body = {"review_token": preview["review_token"]}
    assert client.post("/api/wiring/apply", headers=auth, json=body).status_code == 200
    assert client.post("/api/wiring/apply", headers=auth, json=body).status_code == 409
    assert wiring_calls == ["preview", "apply"]


def test_new_preview_invalidates_old_and_settings_changes_block_apply(client, auth, app, wiring_calls):
    first = client.get("/api/wiring/preview").json()
    second = client.get("/api/wiring/preview").json()
    assert client.post("/api/wiring/apply", headers=auth, json={"review_token": first["review_token"]}).status_code == 409
    revision, config = app.state.store.config()
    app.state.store.save(config, revision)
    assert client.post("/api/wiring/apply", headers=auth, json={"review_token": second["review_token"]}).status_code == 409
    assert "apply" not in wiring_calls
