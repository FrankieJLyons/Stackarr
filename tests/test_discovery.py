from unittest.mock import patch

import httpx
import pytest

from stackarr.discovery import discover, evidence


def docker_runner(monkeypatch, rows, endpoint='unix:///var/run/docker.sock'):
    import json
    import subprocess

    monkeypatch.delenv('DOCKER_HOST', raising=False)
    monkeypatch.setattr('stackarr.discovery.Path.exists', lambda self: False)
    monkeypatch.setattr('stackarr.docker_runtime.executable', lambda: 'docker')
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:] == ['context', 'show']:
            output = 'local'
        elif args[1:3] == ['context', 'inspect']:
            output = endpoint
        else:
            assert args[1:5] == ['--context', 'local', 'ps', '--format']
            assert kwargs['timeout'] == 4
            output = '\n'.join(json.dumps(row) for row in rows)
        return subprocess.CompletedProcess(args, 0, output, '')
    return run, calls


def test_inventory_finds_nonstandard_ports_without_inspecting_secrets(monkeypatch):
    from stackarr.discovery import docker_candidates

    run, calls = docker_runner(monkeypatch, [
        {'image': 'sha256:opaque', 'service': 'sonarr', 'ports': '127.0.0.1:18989->8989/tcp, 0.0.0.0:28989->8989/tcp'},
        {'image': 'lscr.io/linuxserver/radarr:latest', 'service': 'movies', 'ports': '127.0.0.1:17878->7878/tcp'},
        {'image': 'other', 'service': 'sonarr', 'ports': '192.0.2.1:8989->8989/tcp'},
        {'image': 'other', 'service': 'qbittorrent', 'ports': '127.0.0.1:28006->28006/tcp, 0.0.0.0:6881->6881/tcp'},
    ])
    rows, _ = docker_candidates(['sonarr', 'radarr', 'qbittorrent'], runner=run)
    assert rows == {'sonarr': ['http://127.0.0.1:18989', 'http://127.0.0.1:28989'],
                    'radarr': ['http://127.0.0.1:17878'], 'qbittorrent': ['http://127.0.0.1:28006']}
    assert len(calls) == 3 and all('exec' not in call and 'stop' not in call for call in calls)
    assert 'Env' not in str(calls) and 'Mounts' not in str(calls)


def test_inventory_refuses_remote_engine_and_environment_override(monkeypatch):
    from stackarr.discovery import docker_candidates

    run, calls = docker_runner(monkeypatch, [], 'tcp://remote.example:2375')
    rows, notice = docker_candidates(['sonarr'], runner=run)
    assert rows == {} and 'could not' in notice and len(calls) == 2
    monkeypatch.setenv('DOCKER_HOST', 'tcp://remote.example:2375')
    assert docker_candidates(['sonarr'], runner=run)[0] == {}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_docker_hint_does_not_establish_identity_or_send_credentials(monkeypatch):
    run, _ = docker_runner(monkeypatch, [
        {'image': 'other', 'service': 'sonarr', 'ports': '127.0.0.1:18989->8989/tcp'}])
    calls = []

    def response(request):
        calls.append(request)
        assert request.method == 'GET'
        assert 'authorization' not in request.headers and 'x-api-key' not in request.headers
        return httpx.Response(401 if request.url.port == 18989 else 302, headers={'location':'https://example.com'})

    result = await discover(['sonarr'], enabled=True, include_docker=True, runner=run,
                            transport=httpx.MockTransport(response))
    assert [row['state'] for row in result['results']] == ['credentials-required', 'unverified']
    assert all(not row['adopted'] for row in result['results']) and len(calls) == 2


def test_open_port_or_generic_version_is_not_identity():
    assert not evidence("sonarr", b'{"version":"1.0"}')
    assert not evidence("sonarr", b'{"appName":"Radarr","version":"1.0"}')
    assert evidence("sonarr", b'{"appName":"Sonarr","version":"1.0"}')
    assert not evidence("plex", b'<html>Sign in</html>')


@pytest.mark.asyncio
async def test_disabled_discovery_never_probes():
    def deny(request):
        pytest.fail("Disabled discovery must not contact a host")
    assert (await discover(["sonarr"], include_docker=True, runner=lambda *a, **k: pytest.fail('No Docker access'),
                           transport=httpx.MockTransport(deny)))["scope"] == "unavailable"


@pytest.mark.asyncio
async def test_discovery_is_selected_local_bounded_and_without_secrets():
    calls = []

    def response(request):
        calls.append(request)
        assert request.method == "GET" and request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers and "x-api-key" not in request.headers
        if request.url.port == 8989:
            return httpx.Response(401)
        if request.url.port == 7878:
            return httpx.Response(200, text="wrong service")
        raise httpx.ConnectError("private transport detail")

    with patch("stackarr.discovery.Path.exists", return_value=False):
        result = await discover(["sonarr", "radarr", "qbittorrent"], enabled=True, transport=httpx.MockTransport(response))
    assert [row["state"] for row in result["results"]] == ["credentials-required", "unverified", "not-detected"]
    assert len(calls) == 3
    assert not any(row["adopted"] for row in result["results"])
    assert "private transport detail" not in str(result)
