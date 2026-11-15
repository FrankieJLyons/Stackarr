import socket
import ssl
import threading
import time

import httpx
import pytest
import uvicorn
from cryptography import x509

from stackarr.controller import InstallationController
from stackarr.controller_enrollment import HOST, client, enroll
from stackarr.controller_transport import ControllerClient, create_controller_app
from stackarr.server import create_app
from stackarr.store import Store


def test_enrollment_is_private_stable_and_pinned(tmp_path):
    first = enroll(tmp_path / "host")
    key = first["key"].read_bytes()
    cert = first["certificate"].read_bytes()
    assert len(key) == 32
    assert first["private"].parent != first["shared"]
    assert enroll(tmp_path / "host") == first
    assert first["key"].read_bytes() == key
    assert first["certificate"].read_bytes() == cert
    assert HOST in x509.load_pem_x509_certificate(cert).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    ssl.create_default_context(cafile=str(first["certificate"]))
    assert isinstance(client(first["shared"]).certificate, ssl.SSLContext)


def test_partial_enrollment_is_not_replaced(tmp_path):
    shared = tmp_path / "host" / "shared"
    shared.mkdir(parents=True)
    (shared / "rpc.key").write_bytes(b"x" * 32)
    with pytest.raises(ValueError, match="incomplete"):
        enroll(tmp_path / "host")


def test_docker_route_requires_encrypted_pinned_transport():
    with pytest.raises(ValueError, match="HTTPS"):
        ControllerClient("http://host.docker.internal:28010", b"x" * 32)
    with pytest.raises(ValueError, match="certificate"):
        ControllerClient("https://host.docker.internal:28010", b"x" * 32)


def test_probe_connection_error_is_plain_language(tmp_path, monkeypatch, capsys):
    from stackarr.cli import main
    from stackarr.controller_transport import ControllerConnectionError

    class Lost:
        async def request(self, operation):
            raise ControllerConnectionError("Installation connection unavailable. Check progress before trying again")

    monkeypatch.setattr("stackarr.controller_enrollment.client", lambda path: Lost())
    monkeypatch.setattr("sys.argv", ["stackarr", "controller-probe", str(tmp_path)])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 1
    output = capsys.readouterr()
    assert "Installation connection unavailable" in output.err
    assert "Traceback" not in output.err


@pytest.mark.asyncio
async def test_real_tls_listener_accepts_enrolled_client(tmp_path):
    identity = enroll(tmp_path / "host")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    controller = InstallationController(Store(tmp_path / "state"), [], 28000)
    app = create_controller_app(controller, identity["key"].read_bytes(),
                                f"localhost:{port}", run_worker=False)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", access_log=False,
        ssl_certfile=str(identity["certificate"]), ssl_keyfile=str(identity["private"])))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.02)
        assert server.started
        secure = ControllerClient(f"https://localhost:{port}", identity["key"].read_bytes(),
                                  certificate=str(identity["certificate"]))
        assert await secure.request("status") == {"operations": [], "folder_browser": False, "folder_picker": controller.picker_available,
                                                 "actions": [], "companion_login_apps": []}
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_dashboard_reports_connected_controller_install_path(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "rpc.key").write_bytes(b"x" * 32)
    monkeypatch.setenv("STACKARR_CONTROLLER_SHARED", str(shared))

    class Remote:
        async def request(self, operation):
            assert operation == "status"
            return {"operations": [{"id": "a" * 32, "state": "needs-setup", "message": "Ready"}]}

    monkeypatch.setattr("stackarr.controller_enrollment.client", lambda path: Remote())
    app = create_app(tmp_path / "dashboard", origin="http://testserver", background=False)
    with app.state.store.db() as db:
        db.execute("INSERT INTO sessions VALUES(?,?,?)", ("session", "csrf", 9999999999))
    # Session rows store a SHA-256 digest of the browser cookie.
    import hashlib
    with app.state.store.db() as db:
        db.execute("UPDATE sessions SET token=?", (hashlib.sha256(b"browser").hexdigest(),))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 cookies={"stackarr_session": "browser"}) as browser:
        result = (await browser.get("/api/deployments")).json()
    assert result["controller"] == "connected"
    assert result["operations"][0]["state"] == "needs-setup"
    assert result["available"] is True


@pytest.mark.asyncio
async def test_bad_enrollment_keeps_dashboard_available(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "rpc.key").write_bytes(b"bad")
    monkeypatch.setenv("STACKARR_CONTROLLER_SHARED", str(shared))
    app = create_app(tmp_path / "dashboard", origin="http://testserver", background=False)
    assert app.state.store.config()[0] == 1
    import hashlib
    with app.state.store.db() as db:
        db.execute("INSERT INTO sessions VALUES(?,?,?)",
                   (hashlib.sha256(b"browser").hexdigest(), "csrf", 9999999999))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 cookies={"stackarr_session": "browser"}) as browser:
        result = (await browser.get("/api/deployments")).json()
    assert result["controller"] == "unavailable"
    assert result["available"] is False
