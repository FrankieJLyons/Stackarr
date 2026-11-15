"""Independent loopback readiness window, usable before Docker is installed."""

import argparse
import hmac
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .first_run import MODES, inspect
from .first_run_docker import DockerSetup, SetupError


def assets():
    return Path(sys._MEIPASS) / "first_run_assets" if getattr(sys, "frozen", False) else (
        Path(__file__).resolve().parents[1] / "platform/windows/first_run"
    )


class ReadinessServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, inspector=None, docker_setup=None, handoff=None):
        self.key = secrets.token_urlsafe(32)
        self.inspector = inspector or inspect
        self.docker_setup = docker_setup or DockerSetup()
        self.handoff = handoff
        self.check_lock = threading.Lock()
        self.clients = threading.BoundedSemaphore(8)
        self.touched = time.monotonic()
        super().__init__(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"

    @property
    def launch_url(self):
        # The launch capability is in a fragment: not sent in URLs, logs or referrers.
        return self.origin + "/#" + self.key

    def service_actions(self):
        if time.monotonic() - self.touched > 20 * 60 and not self.setup_running():
            threading.Thread(target=self.shutdown, daemon=True).start()

    def setup_running(self):
        return bool(self.docker_setup.worker and self.docker_setup.worker.is_alive()) or bool(
            self.handoff and self.handoff.status()["phase"] == "starting")

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


class Handler(BaseHTTPRequestHandler):
    server_version = "StackarrReadiness"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        pass

    def respond(self, status, body=b"", content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def local_host(self):
        return self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"]

    def do_GET(self):
        if not self.local_host():
            self.respond(403)
            return
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/readiness.css": ("readiness.css", "text/css; charset=utf-8"),
                 "/readiness.js": ("readiness.js", "text/javascript; charset=utf-8")}
        if self.path not in files:
            self.respond(404)
            return
        name, content_type = files[self.path]
        try:
            body = (assets() / name).read_bytes()
        except OSError:
            self.respond(503)
            return
        self.respond(200, body, content_type)

    def do_POST(self):
        valid_key = self.headers.get_all("X-Readiness-Key")
        if (not self.local_host() or self.headers.get_all("Origin") != [self.server.origin]
                or not valid_key or len(valid_key) != 1
                or not hmac.compare_digest(valid_key[0].encode("utf-8"), self.server.key.encode("ascii"))):
            self.respond(403)
            return
        if self.path not in ("/api/check", "/api/close", "/api/docker/review", "/api/docker/start", "/api/docker/status", "/api/docker/cancel", "/api/stackarr/start", "/api/stackarr/status", "/api/stackarr/network"):
            self.respond(404)
            return
        if (self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Content-Length") is None
                or len(self.headers.get_all("Content-Length")) != 1
                or self.headers.get("Content-Type") != "application/json"):
            self.respond(400)
            return
        try:
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 256:
                raise ValueError("Invalid size")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            payload = json.loads(raw)
            fields = {"mode", "review_id", "previous_closed"} if self.path == "/api/docker/start" else {"mode"}
            if not isinstance(payload, dict) or set(payload) != fields or payload["mode"] not in MODES:
                raise ValueError("Invalid mode")
            if self.path == "/api/docker/start" and (
                not isinstance(payload["review_id"], str) or len(payload["review_id"]) > 64
                or type(payload["previous_closed"]) is not bool
            ):
                raise ValueError("Invalid review")
        except (ValueError, TypeError, OSError):
            self.respond(400)
            return
        self.server.touched = time.monotonic()
        if self.path.startswith("/api/stackarr/"):
            if not self.server.handoff:
                self.respond(404)
                return
            try:
                if self.path == "/api/stackarr/network":
                    if self.setup_blocked() or self.server.handoff.status()["phase"] == "starting":
                        raise SetupError("Wait for the current setup step to finish, then open Home network & recovery.")
                    value = self.server.handoff.network()
                elif self.path == "/api/stackarr/start":
                    if self.setup_blocked() or not self.server.check_lock.acquire(blocking=False):
                        raise SetupError("Wait for Docker setup or the current readiness check to finish.")
                    try:
                        value = self.server.handoff.start(payload["mode"], self.server.inspector(payload["mode"]))
                    finally:
                        self.server.check_lock.release()
                else:
                    value = self.server.handoff.status()
                self.respond(200, json.dumps(value).encode())
                if value.get("phase") == "ready":
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
            except SetupError as exc:
                self.respond(409, json.dumps({"message": str(exc)}).encode())
            except Exception:
                self.respond(503, b'{"message":"Stackarr could not open. Check readiness and try again."}')
            return
        if self.path == "/api/close":
            if self.server.setup_running():
                self.respond(409, b'{"message":"Finish or cancel Docker setup before closing this checker."}')
                return
            self.respond(200, b'{"closed":true}')
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path.startswith("/api/docker/"):
            try:
                if (self.server.handoff and self.server.handoff.status()["phase"] == "starting"
                        and self.path in {"/api/docker/review", "/api/docker/start"}):
                    raise SetupError("Wait for Stackarr to finish opening.")
                if self.path == "/api/docker/status":
                    value = self.server.docker_setup.status()
                elif payload["mode"] != "install":
                    raise SetupError("Docker installation is not needed for existing-app connections.")
                elif self.path == "/api/docker/cancel":
                    value = self.server.docker_setup.cancel()
                else:
                    if not self.server.check_lock.acquire(blocking=False):
                        raise SetupError("A readiness check is running. Try again shortly.")
                    try:
                        report = self.server.inspector("install")
                        if self.path == "/api/docker/review":
                            value = self.server.docker_setup.review(report)
                        else:
                            value = self.server.docker_setup.start(payload["review_id"], report, payload["previous_closed"])
                    finally:
                        self.server.check_lock.release()
                self.respond(200, json.dumps(value).encode())
            except SetupError as exc:
                self.respond(409, json.dumps({"message": str(exc)}).encode())
            except Exception:
                self.respond(503, b'{"message":"Docker setup could not finish. Reopen this checker and review its status."}')
            return
        if not self.server.check_lock.acquire(blocking=False):
            self.respond(409, b'{"message":"A check is already running. Try again shortly."}')
            return
        try:
            report = self.server.inspector(payload["mode"])
            if self.server.handoff:
                report = {**report, "integrated": True}
                if report.get("state") == "ready":
                    report["next_step"] = "Continue to Stackarr to choose your apps and review their setup." if payload["mode"] == "install" else "Continue to open the local Stackarr window and connect your existing apps. Docker is not required."
            status, body = 200, json.dumps(report).encode()
        except Exception:
            status, body = 503, b'{"message":"Checks could not finish. Reopen the checker and try again."}'
        finally:
            self.server.check_lock.release()
        self.respond(status, body)

    def setup_blocked(self):
        return self.server.docker_setup.status()["busy"]


def main():
    parser = argparse.ArgumentParser(description="Stackarr first-run readiness preview")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", type=Path, help="Write a new read-only report without opening the window")
    mode.add_argument("--self-test-report", type=Path, help="Run isolated executable checks without contacting Docker")
    parser.add_argument("--mode", choices=MODES, default="install")
    args = parser.parse_args()
    if args.self_test_report:
        from .first_run_smoke import run

        return run(args.self_test_report)
    if args.report:
        report = inspect(args.mode)
        try:
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump({**report, "frozen": bool(getattr(sys, "frozen", False))}, stream, indent=2)
        except OSError:
            return 2
        return 0 if report["state"] == "ready" else 1
    try:
        with ReadinessServer() as server:
            try:
                opened = webbrowser.open(server.launch_url)
            except webbrowser.Error:
                opened = False
            if not opened:
                # A frozen windowed executable has no terminal; show a useful fallback.
                import tkinter.messagebox

                tkinter.messagebox.showinfo("Open Stackarr readiness", "Open this address in your usual browser:\n\n" + server.launch_url)
            server.serve_forever(poll_interval=0.3)
    except OSError:
        import tkinter.messagebox

        tkinter.messagebox.showerror("Stackarr readiness could not open", "The local check page could not start. Close the checker, check your local security software's permissions and reopen it.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
