"""Private, fixed-argument handoff from readiness to the main package."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

from .first_run_docker import SetupError, operation_lock, ordinary


def folder(path):
    path = ordinary(Path(path))
    if not path.is_absolute() or path == Path(path.anchor):
        raise SetupError("Choose a dedicated absolute Stackarr data folder.")
    return path


def local_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}
            or not parsed.port or parsed.username or parsed.password or parsed.query
            or parsed.path not in {"", "/"}):
        raise SetupError("Stackarr returned an unexpected local address.")
    return value


class PackageStart:
    def __init__(self, package_root, state_root, connect_root, port=28000, controller_port=28010, *, media_folder=None, runner=None):
        self.package_root = folder(package_root)
        self.state_root, self.connect_root = folder(state_root), folder(connect_root)
        if (self.state_root == self.connect_root or self.state_root in self.connect_root.parents
                or self.connect_root in self.state_root.parents):
            raise SetupError("Docker and local dashboard data need separate folders.")
        self.media_folder = folder(media_folder) if media_folder else None
        if self.media_folder and not self.media_folder.is_dir():
            raise SetupError("Choose an existing media folder.")
        if any(type(p) is not int or not 1 <= p <= 65535 for p in (port, controller_port)):
            raise SetupError("Choose valid Stackarr ports.")
        self.port, self.controller_port = port, controller_port
        self.runner = runner or self.launch
        self.lock = threading.Lock()
        self.worker = None
        self.value = {"phase": "idle"}

    def status(self):
        with self.lock:
            return dict(self.value)

    def network(self):
        from .self_update import package

        if not (self.state_root / "installation.json").is_file():
            raise SetupError("Set up Stackarr first, then reopen Start Stackarr for Home network & recovery.")
        package(self.package_root)
        subprocess.Popen([str(self.package_root / "StackarrPreview.exe"), "--lan-setup", str(self.state_root)],
                         env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"},
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return {"opened": True, "message": "Home network & recovery is opening in a separate local window. Your app settings stay in place."}

    def start(self, mode, report):
        if mode not in {"install", "connect"} or report.get("mode") != mode or report.get("state") != "ready":
            raise SetupError("Check readiness again before continuing to Stackarr.")
        with self.lock:
            if self.value["phase"] in {"starting", "ready"}:
                return dict(self.value)
            self.value = {"phase": "starting", "message": "Opening Stackarr. Your app choices and installation review come next."}
            self.worker = threading.Thread(target=self.execute, args=(mode,), daemon=True)
            self.worker.start()
            return dict(self.value)

    def execute(self, mode):
        root = self.state_root if mode == "install" else self.connect_root
        identity = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:20]
        try:
            with operation_lock(root.parent / (".stackarr-start-" + identity)):
                value = self.runner(mode)
                if value.get("review") in {"repair", "reinstall"}:
                    with self.lock:
                        self.value = {"phase": "review-required", "message": "Review " + value["review"] + " in the local Stackarr window, then choose Continue to Stackarr again. Your retained settings stay in place."}
                    return
                url = local_url(value["url"])
            with self.lock:
                self.value = {"phase": "ready", "url": url, "mode": mode}
        except Exception:
            with self.lock:
                checks = "Docker and folder access" if mode == "install" else "the local Stackarr window and folder access"
                self.value = {"phase": "failed", "message": "Stackarr could not open. Check the complete package, " + checks + ", then choose Continue to Stackarr again. Saved settings and media are retained."}

    def launch(self, mode):
        from .self_update import package

        # Verify all package payloads before executing its script or child binary.
        package(self.package_root)
        exe = self.package_root / "StackarrPreview.exe"
        system = os.environ.get("SystemRoot")
        if os.name != "nt" or not system or not Path(system).is_absolute():
            raise SetupError("This packaged launcher requires Windows.")
        environment = dict(os.environ)
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        environment["STACKARR_PACKAGE_ROOT"] = str(self.package_root)
        for key in ("STACKARR_DATA", "STACKARR_ORIGIN", "STACKARR_CONTROLLER_SHARED", "STACKARR_UPDATE_CHECKING"):
            environment.pop(key, None)
        with tempfile.TemporaryDirectory(prefix="stackarr-handoff-") as temporary:
            report = Path(temporary) / "result.json"
            if mode == "install":
                powershell = Path(system) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                command = [str(powershell), "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
                    str(self.package_root / "Start-StackarrPreview.ps1"), "-StateDirectory", str(self.state_root),
                    "-Port", str(self.port), "-ControllerPort", str(self.controller_port), "-NoBrowser", "-ResultFile", str(report)]
                if self.media_folder:
                    command += ["-MediaFolder", str(self.media_folder)]
                result = subprocess.run(command, env=environment, capture_output=True, timeout=300,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    raise SetupError("Packaged startup did not finish.")
            else:
                child = subprocess.Popen([str(exe), "--data-directory", str(self.connect_root),
                    "--launcher-ready-report", str(report), "--no-browser"], env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                deadline = time.monotonic() + 60
                while not report.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.1)
            if not report.is_file() or report.is_symlink() or report.stat().st_size > 8192:
                raise SetupError("Stackarr did not return a local address.")
            return json.loads(report.read_text(encoding="utf-8-sig"))


def main(args):
    from .first_run_docker import DockerSetup
    from .first_run_server import ReadinessServer
    from .launcher import data_directory

    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    state = args.data_directory or str(Path(os.environ["LOCALAPPDATA"]) / "Stackarr/DockerPreview")
    handoff = PackageStart(base, state, args.connect_directory or data_directory(), args.dashboard_port, args.controller_port,
                           media_folder=args.media_folder)
    setup = DockerSetup(folder(args.prerequisite_directory)) if args.prerequisite_directory else DockerSetup()
    with ReadinessServer(docker_setup=setup, handoff=handoff) as server:
        if args.first_run_report:
            with Path(args.first_run_report).open("x", encoding="utf-8") as output:
                json.dump({"url": server.launch_url, "pid": os.getpid()}, output)
        if not args.no_browser:
            import webbrowser

            if not webbrowser.open(server.launch_url):
                import tkinter.messagebox

                tkinter.messagebox.showinfo("Open Stackarr", "Open this address in your browser:\n\n" + server.launch_url)
        server.serve_forever(poll_interval=.3)
    return 0
