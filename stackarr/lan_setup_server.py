"""Independent local browser window; available even when the dashboard is down."""

import hmac
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .first_run_server import Handler as LocalHandler
from .lan_setup import LanSetup, public_error

ASSETS = Path(__file__).parent / "static/lan_setup"


class LanSetupServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, setup):
        self.setup = setup
        self.key = secrets.token_urlsafe(32)
        self.action_lock = threading.Lock()
        self.clients = threading.BoundedSemaphore(8)
        self.touched = time.monotonic()
        super().__init__(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"

    @property
    def launch_url(self):
        return self.origin + "/#" + self.key

    def service_actions(self):
        if time.monotonic() - self.touched > 1200 and not self.action_lock.locked() and not self.setup.child:
            threading.Thread(target=self.shutdown, daemon=True).start()

    def process_request(self, request, client_address):
        if not self.clients.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.clients.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.clients.release()


class Handler(LocalHandler):
    server_version = "StackarrHomeNetwork"

    def do_GET(self):
        if not self.local_host():
            self.respond(403)
            return
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/setup.css": ("setup.css", "text/css; charset=utf-8"),
                  "/setup.js": ("setup.js", "text/javascript; charset=utf-8")}
        if self.path not in assets:
            self.respond(404)
            return
        name, content_type = assets[self.path]
        self.respond(200, (ASSETS / name).read_bytes(), content_type)

    def do_POST(self):
        keys = self.headers.get_all("X-LAN-Key")
        if (not self.local_host() or self.headers.get_all("Origin") != [self.server.origin]
                or not keys or len(keys) != 1 or not hmac.compare_digest(keys[0].encode(), self.server.key.encode())):
            self.respond(403)
            return
        actions = {"status", "choices", "prepare", "review", "apply", "certificate", "check", "start", "stop", "close"}
        action = self.path.removeprefix("/api/")
        if self.path != "/api/" + action or action not in actions:
            self.respond(404)
            return
        lengths = self.headers.get_all("Content-Length")
        try:
            if (self.headers.get_all("Transfer-Encoding") or not lengths or len(lengths) != 1
                    or self.headers.get("Content-Type") != "application/json" or not 0 < int(lengths[0]) <= 2048):
                raise ValueError()
            raw = self.rfile.read(int(lengths[0]))
            if len(raw) != int(lengths[0]):
                raise ValueError()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
        except (TypeError, ValueError, OSError):
            self.respond(400)
            return
        if not self.server.action_lock.acquire(blocking=False):
            self.respond(409, b'{"message":"A setup step is running. Wait for it to finish, then try again."}')
            return
        self.server.touched = time.monotonic()
        try:
            if action == "close":
                if value:
                    raise ValueError("Close setup without additional options.")
                job = self.server.setup.job()
                if job and job["phase"] not in {"succeeded", "rolled-back", "failed-recovered", "needs-recovery"}:
                    raise ValueError("Wait for the current settings operation to finish before closing setup.")
                self.server.setup.stop()
                result = {"closed": True}
            else:
                result = self.server.setup.dispatch(action, value)
            self.respond(200, json.dumps(result).encode())
            if action == "close":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
        except Exception as exc:
            self.respond(409, json.dumps({"message": public_error(exc)}).encode())
        finally:
            self.server.action_lock.release()


def run(state, workspace, caddy=None, report=None, no_browser=False):
    from .launcher import instance_lock
    from .self_update import read, write

    setup = LanSetup(state, workspace, caddy)
    window = setup.root / "window-private.json"
    if window.is_file():
        try:
            url = read(window)["url"]
            parsed = urlsplit(url)
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                    or parsed.path != "/" or parsed.query or parsed.username or parsed.password
                    or len(parsed.fragment) != 43):
                raise ValueError()
            origin = f"http://127.0.0.1:{parsed.port}"
            response = httpx.post(origin + "/api/status", headers={"Origin": origin, "X-LAN-Key": parsed.fragment},
                                  json={}, trust_env=False, timeout=3)
            if response.status_code == 200 and response.json()["local_url"] == setup.local:
                if report:
                    with Path(report).open("x", encoding="utf-8") as output:
                        json.dump({"url": url, "reused": True}, output)
                if not no_browser:
                    webbrowser.open(url)
                return 0
        except (KeyError, TypeError, ValueError, OSError, httpx.HTTPError):
            pass
    lock = instance_lock(setup.root)
    try:
        with LanSetupServer(setup) as server:
            write(window, {"url": server.launch_url})
            if report:
                with Path(report).open("x", encoding="utf-8") as output:
                    json.dump({"url": server.launch_url, "pid": os.getpid()}, output)
            if not no_browser:
                webbrowser.open(server.launch_url)
            server.serve_forever(poll_interval=.3)
    finally:
        setup.stop()
        window.unlink(missing_ok=True)
        lock.close()
    return 0
