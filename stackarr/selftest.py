"""Packaged-runtime smoke check using temporary state and loopback only."""

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from . import __version__
from .server import create_app


def run(report_path):
    checks = []
    passed = False
    guided_lan = False
    signin_startup = False
    try:
        import tkinter

        interpreter = tkinter.Tcl()
        assert interpreter.eval("info patchlevel")
        checks.append("bundled Tcl initialized")
        from .bootstrap import libraries
        from .deployment import images
        from .finish_setup import FILES, finish
        from .folder_picker import FolderPicker

        assert {"plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr"} <= set(images())
        assert callable(libraries) and FolderPicker().take() is None
        checks.append("packaged pinned images and installer modules")
        from .onboarding import AppChoice
        from .quality import select_profile

        assert AppChoice(quality_profile="HD-1080p").quality_profile == "HD-1080p"
        assert select_profile([{"id": 1, "name": "Any"}, {"id": 4, "name": "HD-1080p"}], "HD-1080p")["id"] == 4
        checks.append("packaged explicit movie/TV request quality and exact profile selection")
        from .config import Config
        from .setup_readiness import build as build_journey

        journey = build_journey({"revision": 1, "draft": {}}, Config())
        assert journey["next_action"]["id"] == "choose-apps" and not journey["ready_to_watch"]
        assert (Path(__file__).parent / "static/setup_journey.js").is_file()
        checks.append("packaged saved setup journey without unverified playback claims")
        from .bundled_images import catalog as bundled_catalog

        assert bundled_catalog()["seerr"]["image"] == images()["seerr"]
        checks.append("packaged Seerr security backport image catalog")
        from .first_run_package import PackageStart
        from .first_run_server import assets

        assert callable(PackageStart.start) and (assets() / "readiness.js").is_file()
        from .windows_startup import Registration, resume

        assert callable(Registration.enable) and callable(Registration.disable) and callable(resume)
        assert callable(PackageStart.startup)
        signin_startup = True
        checks.append("packaged opt-in sign-in startup and local review")
        checks.append("packaged integrated readiness, reviewed Docker setup and continuation")
        assert set(FILES) == {"plex", "seerr"} and callable(finish)
        checks.append("packaged account connection module available without Docker calls")
        from .account_setup import Accounts

        assert callable(Accounts.review) and callable(Accounts.apply)
        checks.append("packaged reviewed Plex libraries and requests account setup")
        from .arr_logins import prepare as prepare_logins
        from .backup_policy import BackupPlans, BackupPolicyIntent
        from .companion_maintenance import checkpoint as companion_checkpoint
        from .companion_maintenance import version as companion_version
        from .companions import APPS, Companions
        from .controller_connections import finish_owned, finish_plex
        from .controller_enrollment import client, enroll
        from .docker_runtime import inspect
        from .host_recovery import HostBackups, Recovery
        from .indexers import ProviderSource, Source, SourceCheck
        from .indexers import catalog as source_catalog
        from .indexers import validate as validate_source
        from .kuma import Kuma
        from .media_folders import grant
        from .onboarding import SetupDraft
        from .plex_wiring import build as prepare_plex_refresh
        from .ports import PortsUnavailable, ensure, suggestions
        from .recovery_wizard import command as recovery_command
        from .seerr_wiring import build as prepare_seerr
        from .self_update import PROTOCOL, SelfUpdates
        from .updates import catalog

        assert callable(finish_owned) and callable(finish_plex) and callable(client) and callable(enroll)
        assert callable(prepare_logins) and Source(name="Fixture", feed_url="http://fixture.example/api")
        assert ProviderSource(provider_id="a" * 24, name="Fixture").fields == {}
        assert SourceCheck(query=" Original sample ", media_type="tv").query == "Original sample"
        assert callable(source_catalog) and callable(validate_source)
        checks.append("packaged guided source models, catalog and bounded search diagnostics")
        assert callable(prepare_seerr)
        assert callable(prepare_plex_refresh)
        checks.append("packaged native Plex import notifications and availability scheduling")
        assert set(catalog()["apps"]) == set(images())
        assert callable(companion_checkpoint) and callable(companion_version)
        checks.append("packaged immutable update catalog and recovery modules")
        assert BackupPolicyIntent().keep == 7 and callable(BackupPlans.tick)
        checks.append("packaged backup schedules, retention and second-disk recovery modules")
        assert callable(HostBackups.execute) and callable(Recovery.execute) and callable(recovery_command)
        checks.append("packaged whole-host checkpoints and empty-installation recovery entry points")
        assert PROTOCOL == 1 and callable(SelfUpdates.execute) and callable(SelfUpdates.recover)
        checks.append("packaged independent Stackarr self-update, rollback and startup recovery")
        from .runtime_storage import check as check_runtime_storage
        from .self_repair import SelfRepair

        assert callable(SelfRepair.review) and callable(SelfRepair.recover) and callable(check_runtime_storage)
        checks.append("packaged runtime repair and storage preflight")
        assert APPS <= set(images()) and callable(Companions.execute) and callable(Kuma.login)
        checks.append("packaged protected companion setup and bounded Kuma protocol")
        assert SetupDraft().port_mode == "automatic" and callable(grant) and callable(ensure)
        checks.append("packaged automatic ports, conflict recovery and host-consented media folders")
        with socket.socket() as occupied:
            occupied.bind(("0.0.0.0", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            draft = SetupDraft(apps=["seerr"], choices={"seerr": {"port": port}})
            try:
                ensure(draft)
            except PortsUnavailable:
                pass
            else:
                raise AssertionError("Packaged port checks failed to reject an occupied wildcard listener")
            assert suggestions(draft)[0]["port"] != port
        checks.append("packaged occupied-port rejection without contacting the listener")
        assert inspect()["state"] == "not-checked"
        checks.append("packaged private controller, owned-app handoff and read-only runtime check")
        from .docker_failures import classify
        from .docker_networks import estimate

        assert callable(estimate) and classify("unexpected EOF", downloading=True)[2]
        checks.append("packaged read-only network capacity and interrupted-download recovery")
        from .install_ports import InstallPorts

        assert callable(InstallPorts.reconcile) and callable(InstallPorts.approve)
        checks.append("packaged retained-settings final-start port recovery")
        from .seerr_storage import prepare as prepare_seerr_storage

        assert callable(prepare_seerr_storage)
        assert (Path(__file__).parent / "static/setup_accounts.js").is_file()
        checks.append("packaged verified Seerr storage and Plex account guidance")
        from .app_maintenance import AppMaintenance

        assert callable(AppMaintenance.execute) and callable(AppMaintenance.recover)
        checks.append("packaged single-app repair, retained-data removal and reviewed recovery")
        from .reinstall_wizard import approve as approve_reinstall
        from .reinstall_wizard import wizard as reinstall_wizard
        from .self_removal import SelfRemoval

        assert callable(SelfRemoval.execute_remove) and callable(SelfRemoval.recover_reinstall)
        assert callable(approve_reinstall) and callable(reinstall_wizard)
        checks.append("packaged retained-data Stackarr removal and reviewed native reinstall")
        from .lan_setup import LanSetup, bundled_caddy, checked_caddy
        from .lan_setup_server import LanSetupServer

        if bundled_caddy().is_file():
            checked_caddy(bundled_caddy())
            guided_lan = True
            checks.append("pinned Caddy bundled for guided home-network setup")
        with tempfile.TemporaryDirectory(prefix="stackarr-lan-smoke-") as directory:
            state = Path(directory) / "installation"
            state.mkdir()
            (state / "installation.json").write_text(json.dumps({"owner":"stackarr-docker-preview-v1", "port":29123}))
            lan_setup = LanSetup(state, Path(directory) / "network", network_reader=lambda: [])
            with LanSetupServer(lan_setup) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    with httpx.Client(base_url=server.origin, trust_env=False) as client:
                        assert "Home network" in client.get("/").text
                        assert client.get("/setup.js").status_code == 200
                        assert client.get("/setup.css").status_code == 200
                        assert client.post("/api/status", json={}).status_code == 403
                        status = client.post("/api/status", json={}, headers={"Origin":server.origin, "X-LAN-Key":server.key}).json()
                        assert status["physical_status"] == "pending" and not status["prepared"]
                finally:
                    server.shutdown()
                    thread.join(3)
            assert not (state / "stackarr-runtime.json").exists()
        checks.append("packaged guided LAN window, private local launch and untouched installation")
        with tempfile.TemporaryDirectory(prefix="stackarr-package-test-") as directory, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            app = create_app(Path(directory), origin=origin, background=False, host_checks=True, host_install=True)
            assert app.state.deployments.rows() == [] and app.state.deployments.actions.rows() == []
            checks.append("packaged local installer and app-action journal initialized without Docker calls")
            app.state.store.save(app.state.store.config()[1], 1, {"sonarr": {"api_key": "synthetic-smoke-value"}})
            assert app.state.store.secret("sonarr")["api_key"] == "synthetic-smoke-value"
            checks.append("SQLite and credential encryption round trip")
            server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, proxy_headers=False))
            thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
            thread.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    if not thread.is_alive():
                        raise RuntimeError("Server stopped during startup")
                    time.sleep(0.05)
                with httpx.Client(base_url=origin, trust_env=False, timeout=5) as client:
                    assert client.get("/healthz").json()["status"] == "ok"
                    assert client.get("/api/config").status_code == 401
                    assert "Stackarr" in client.get("/").text
                    for asset in ("app.js", "home.js", "home.css", "setup.js", "setup_choices.js", "setup_journey.js", "launcher.js", "help.js", "app.css", "theme.css", "favicon.svg"):
                        assert client.get("/static/" + asset).status_code == 200
                    response = client.post("/api/setup", headers={"Origin": origin}, json={
                        "password": "synthetic packaged journey password",
                        "setup_token": (Path(directory) / "setup-token").read_text(encoding="utf-8")})
                    assert response.status_code == 200
                    assert client.post("/api/login", headers={"Origin": origin}, json={
                        "password": "synthetic packaged journey password"}).status_code == 200
                    assert client.get("/api/onboarding/journey").json()["next_action"]["id"] == "choose-apps"
                    assert client.get("/api/deployments").json()["journey"]["selected_apps"] == []
                    assert client.get("/api/home").status_code == 409
                    checks.append("packaged authenticated journey and deployment status without Docker calls")
                checks.append("loopback server, authentication boundary and packaged assets")
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                if thread.is_alive():
                    raise RuntimeError("Server did not stop")
            checks.append("server shut down and temporary data released")
        passed = True
    except Exception:
        # Do not emit filesystem paths, exception payloads or credentials.
        checks.append("runtime smoke check failed")
    Path(report_path).write_text(json.dumps({"passed": passed, "version": __version__, "signin_startup": signin_startup,
        "frozen": bool(getattr(sys, "frozen", False)), "guided_lan": guided_lan,
        "checks": checks, "scope": "temporary data and loopback; no app installation, Docker or reboot test"}, indent=2), encoding="utf-8")
    return 0 if passed else 1
