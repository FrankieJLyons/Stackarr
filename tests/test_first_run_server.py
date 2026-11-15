import http.client
import json
import socket
import threading
from types import SimpleNamespace

import pytest

from stackarr.first_run_server import ReadinessServer


@pytest.fixture
def running(tmp_path):
    from stackarr.first_run_docker import DockerSetup

    calls = []
    with ReadinessServer(lambda mode: calls.append(mode) or {"state": "ready", "mode": mode}) as server:
        server.docker_setup = DockerSetup(root=tmp_path / "prerequisites")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, calls
        finally:
            server.shutdown()
            thread.join(timeout=3)


def request(server, method="POST", path="/api/check", body=None, **headers):
    if body is None:
        body = "" if method == "GET" else json.dumps({"mode": "install"})
    prepared = {"Origin": server.origin, "X-Readiness-Key": server.key, "Content-Type": "application/json"}
    prepared.update(headers)
    payload=body.encode('utf-8') if isinstance(body,str) else body
    prepared={"Host":f"127.0.0.1:{server.server_port}","Content-Length":str(len(payload)),**prepared}
    message=(method+' '+path+' HTTP/1.1\r\n'+''.join(str(k)+': '+str(v)+'\r\n' for k,v in prepared.items())+'\r\n').encode('latin-1')+payload
    # A rejected header can close the connection before http.client's separate
    # body write reaches Windows. Send the bounded fixture request together;
    # retain the strict 403/no-probe assertions rather than accepting a reset.
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=4) as connection:
        connection.sendall(message)
        response=http.client.HTTPResponse(connection)
        response.begin()
        return response.status,dict(response.getheaders()),response.read()


def test_page_does_not_probe_and_capability_never_appears_in_html(running):
    server, calls = running
    status, headers, body = request(server, "GET", "/")
    assert status == 200 and not calls
    assert server.key.encode() not in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "no-referrer" and headers["Cache-Control"] == "no-store"
    assert server.launch_url.endswith("/#" + server.key)


@pytest.mark.parametrize("headers", [{"Origin": "https://untrusted.invalid"}, {"Origin": "null"},
                                      {"X-Readiness-Key": ""}, {"X-Readiness-Key": "wrong"},
                                      {"X-Readiness-Key": "\xff"}, {"Host": "untrusted.invalid"}])
def test_cross_site_and_unauthorized_checks_are_rejected_before_probes(running, headers):
    server, calls = running
    assert request(server, **headers)[0] == 403 and not calls


@pytest.mark.parametrize("body", ['{"mode":"unknown"}', '{"mode":[]}', '[]', '{}',
                                   '{"mode":"install","path":"arbitrary"}', 'x' * 129])
def test_only_bounded_fixed_checks_are_accepted(running, body):
    server, calls = running
    assert request(server, body=body)[0] == 400 and not calls


def test_routes_are_fixed_and_report_requires_same_origin_launch(running):
    server, calls = running
    assert request(server, "GET", "/../pyproject.toml")[0] == 404
    assert request(server, "GET", "/api/check")[0] == 404
    assert request(server, "POST", "/api/install")[0] == 404
    assert request(server, **{"Content-Type": "text/plain"})[0] == 400
    status, _, body = request(server)
    assert status == 200 and json.loads(body)["mode"] == "install" and calls == ["install"]


def test_duplicate_content_length_and_missing_origin_rejected(running):
    server, calls = running
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
    conn.putrequest("POST", "/api/check")
    conn.putheader("X-Readiness-Key", server.key)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", "0")
    conn.endheaders()
    assert conn.getresponse().status == 403
    conn.close()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
    conn.putrequest("POST", "/api/check")
    for key, value in (("Origin", server.origin), ("X-Readiness-Key", server.key),
                       ("Content-Type", "application/json"), ("Content-Length", "2"), ("Content-Length", "2")):
        conn.putheader(key, value)
    conn.endheaders(b"{}")
    assert conn.getresponse().status == 400 and not calls
    conn.close()


def test_exception_is_redacted_and_lock_is_released(running):
    server, _ = running

    def fail(mode):
        raise RuntimeError("sensitive path and credentials")

    server.inspector = fail
    status, _, body = request(server)
    assert status == 503 and b"sensitive" not in body
    assert not server.check_lock.locked()


def test_overlapping_checks_are_bounded(running):
    server, calls = running
    server.check_lock.acquire()
    try:
        assert request(server)[0] == 409 and not calls
    finally:
        server.check_lock.release()


def test_close_does_not_probe_or_install(running):
    server, calls = running
    status, _, body = request(server, path="/api/close")
    assert status == 200 and json.loads(body)["closed"] and not calls


@pytest.mark.parametrize("route", ["review", "start", "status", "cancel"])
def test_prerequisite_actions_need_the_same_private_launch(running, route):
    server, calls = running
    assert request(server, path="/api/docker/" + route, **{"Origin": "https://untrusted.invalid"})[0] == 403
    assert not calls


def test_installer_route_rejects_arbitrary_commands_and_existing_app_mode(running):
    server, calls = running
    body = json.dumps({"mode": "install", "review_id": "review", "previous_closed": False, "command": "arbitrary"})
    assert request(server, path="/api/docker/start", body=body)[0] == 400
    assert request(server, path="/api/docker/review", body='{"mode":"connect"}')[0] == 409
    assert not calls


def test_active_prerequisite_worker_cannot_be_closed(running):
    server, calls = running
    server.docker_setup.worker = SimpleNamespace(is_alive=lambda: True)
    assert request(server, path="/api/close")[0] == 409 and not calls


def test_network_recovery_handoff_requires_private_launch_and_fixed_installation(running):
    server, calls = running
    launches = []
    server.handoff = SimpleNamespace(status=lambda:{"phase":"idle"}, network=lambda:launches.append(True) or {"opened":True})
    route = "/api/stackarr/network"
    assert request(server, path=route, **{"Origin":"https://untrusted.invalid"})[0] == 403
    assert request(server, path=route, body='{"mode":"install","state":"another-installation"}')[0] == 400
    assert not launches
    assert request(server, path=route)[0] == 200 and launches == [True] and not calls
