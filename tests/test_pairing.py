from fastapi.testclient import TestClient

from stackarr.pairing import PairingGate
from stackarr.server import create_app


def test_expiry_and_replay():
    now = [0]
    gate = PairingGate(lambda: now[0])
    token, code = gate.request()
    assert not gate.authorized(token)
    assert not gate.approve("wrong")
    assert gate.approve(code)
    assert gate.authorized(token)
    assert not gate.authorized("wrong")
    now[0] = 121
    assert not gate.authorized(token)
    assert gate.display_code() is None
    new_token, _ = gate.request()
    gate.revoke()
    assert not gate.authorized(new_token)


def test_launcher_approval_is_bound_to_browser_and_setup_only(tmp_path):
    gate = PairingGate()
    app = create_app(tmp_path, origin="http://testserver", background=False, pairing=gate)
    headers = {"Origin": "http://testserver"}
    body = {"password": "synthetic launcher password"}
    with TestClient(app) as browser, TestClient(app) as stranger:
        assert browser.post("/api/launcher/pair").status_code == 403
        paired = browser.post("/api/launcher/pair", headers=headers)
        assert paired.status_code == 200
        assert "httponly" in paired.headers["set-cookie"].lower()
        assert browser.post("/api/setup", json=body, headers=headers).status_code == 403
        assert gate.approve(paired.json()["code"])
        assert not stranger.get("/api/session").json()["setup_approved"]
        assert stranger.post("/api/setup", json=body, headers=headers).status_code == 403
        assert browser.post("/api/setup", json=body, headers=headers).status_code == 200
        assert browser.get("/api/config").status_code == 401
        assert gate.display_code() is None
        assert browser.post("/api/launcher/pair", headers=headers).status_code == 404
        assert browser.post("/api/login", json=body, headers=headers).status_code == 200


def test_plain_server_does_not_expose_launcher_pairing(client):
    assert client.post("/api/launcher/pair", headers={"Origin": "http://testserver"}).status_code == 404
