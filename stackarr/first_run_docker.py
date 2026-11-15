"""Reviewed Docker prerequisite setup, independent of Stackarr's app installer."""

import contextlib
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .docker_runtime import executable

RELEASE = {
    "version": "4.95.0", "build": "242831", "bytes": 636811696,
    "url": "https://desktop.docker.com/win/main/amd64/242831/Docker%20Desktop%20Installer.exe",
    "sha256": "73431db38491f770543880366228a23c993f84d1e8e045f56d83b8a98940cf76",
    "source": "https://docs.docker.com/desktop/release-notes/",
    "checksum_source": "https://desktop.docker.com/win/main/amd64/242831/checksums.txt",
}
MESSAGES = {
    "idle": "Review Docker installation before downloading anything.",
    "downloading": "Downloading Docker Desktop from Docker's official server.",
    "verifying": "Checking the download checksum and Docker publisher signature.",
    "installing": "Docker's installer is open. Follow its prompts and keep this page open.",
    "complete": "Docker installation finished. Open Docker Desktop from Start, complete its setup prompts, then choose Check again.",
    "restart-needed": "Docker's installer requested a Windows restart. Save your work, restart when convenient and reopen this readiness application.",
    "cancelled": "Download cancelled. You can review installation again when ready.",
    "failed": "Docker setup did not finish. Review the official setup guide, then try again. Existing Docker installations are preserved.",
    "verification-failed": "The download could not be verified. It was not run. Check your connection and review installation again.",
    "interrupted": "An earlier setup was interrupted. Complete or close any Docker installer still open, then check readiness before reviewing another attempt.",
    "already-installed": "Docker is now installed. Open Docker Desktop and choose Check again.",
}
ACTIVE = {"downloading", "verifying", "installing"}


class SetupError(ValueError):
    pass


def ordinary(path):
    """Do not follow a retained setup directory through a link or junction."""
    path = Path(path)
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise SetupError("The setup folder needs inspection before it can be used.")
    return path


def directory():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise SetupError("The local application-data folder is unavailable.")
    return ordinary(Path(base) / "Stackarr/first-run/docker")


def present():
    if executable():
        return True
    for variable, relative in (("LOCALAPPDATA", "Programs/DockerDesktop/Docker Desktop.exe"),
                               ("ProgramFiles", "Docker/Docker/Docker Desktop.exe")):
        base = os.environ.get(variable)
        if base and Path(base).is_absolute() and (Path(base) / relative).is_file():
            return True
    if os.name == "nt":
        import winreg

        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop"):
                    return True
            except FileNotFoundError:
                pass
            except OSError:
                # A denied installed-app record is not evidence that Docker is missing.
                raise SetupError("Docker's installed-app record could not be checked.") from None
    return False


@contextlib.contextmanager
def operation_lock(root):
    ordinary(root)
    root.mkdir(parents=True, exist_ok=True)
    path = ordinary(root / "operation.lock")
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SetupError("Docker setup is already running in another window.") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class DockerRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "desktop.docker.com":
            raise SetupError("Docker download redirected outside its approved server.")
        return super().redirect_request(request, fp, code, message, headers, url)


def download(path, update, cancelled):
    opener = urllib.request.build_opener(DockerRedirects())
    total = 0
    started = time.monotonic()
    with opener.open(RELEASE["url"], timeout=30) as response, ordinary(path).open("xb") as output:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != RELEASE["bytes"]:
            raise SetupError("Unexpected installer size")
        while True:
            if cancelled.is_set():
                return False
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > RELEASE["bytes"] or time.monotonic() - started > 30 * 60:
                raise SetupError("Docker download exceeded its limit")
            output.write(block)
            update(total)
        output.flush()
        os.fsync(output.fileno())
    if total != RELEASE["bytes"]:
        raise SetupError("Incomplete Docker download")
    return True


def verify_signature(path, *, runner=None):
    system = os.environ.get("SystemRoot")
    if os.name != "nt" or not system or not Path(system).is_absolute():
        raise SetupError("Publisher verification requires Windows")
    script = r"""$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:STACKARR_PREREQUISITE_FILE; [ordered]@{status=[string]$s.Status;subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"""
    result = (runner or subprocess.run)(
        [str(Path(system) / "System32/WindowsPowerShell/v1.0/powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "STACKARR_PREREQUISITE_FILE": str(path),
             "PSModulePath": str(Path(system) / "System32/WindowsPowerShell/v1.0/Modules")}, capture_output=True, text=True,
        timeout=60, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode or len(result.stdout) > 8192:
        raise SetupError("Publisher verification failed")
    signature = json.loads(result.stdout)
    if (signature.get("status") != "Valid" or not re.search(r"(?:^|,\s*)O=Docker Inc(?:,|$)", signature.get("subject", ""))):
        raise SetupError("The Docker publisher could not be verified")


@contextlib.contextmanager
def payload_lock(path):
    """Keep the verified executable from being replaced before CreateProcess."""
    if os.name != "nt":
        raise SetupError("Docker installation requires Windows")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise SetupError("The installer could not be opened exclusively for verification")
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def launch(path):
    # Interactive vendor installer; no license acceptance, quiet mode or reboot command.
    process = subprocess.Popen([str(path), "install", "--user"], creationflags=subprocess.CREATE_NO_WINDOW)
    return process.wait()


class DockerSetup:
    def __init__(self, root=None, *, exists=None, downloader=None, signer=None, launcher=None, locker=None):
        self.root = Path(root) if root is not None else None
        self.exists = exists or present
        self.downloader, self.signer = downloader or download, signer or verify_signature
        self.launcher, self.locker = launcher or launch, locker or payload_lock
        self.mutex = threading.RLock()
        self.worker = None
        self.cancelled = threading.Event()
        self.reviewed = None

    def home(self):
        path = self.root if self.root is not None else directory()
        if not path.is_absolute():
            raise SetupError("Choose an absolute prerequisite setup directory.")
        return ordinary(path)

    def status(self):
        with self.mutex:
            root = self.home()
            path = ordinary(root / "job.json")
            if not path.exists():
                return {"phase": "idle", "message": MESSAGES["idle"], "busy": False}
            try:
                if path.stat().st_size > 16384:
                    raise ValueError("Invalid journal")
                saved = json.loads(path.read_text(encoding="utf-8"))
                phase = saved["phase"]
                if phase not in MESSAGES or saved["version"] != RELEASE["version"]:
                    raise ValueError("Invalid journal")
                if phase in ACTIVE and not (self.worker and self.worker.is_alive()):
                    try:
                        with operation_lock(root):
                            phase = "interrupted"
                    except SetupError:
                        pass  # A second readiness process owns the active operation.
                received = saved.get("downloaded", 0)
                if type(received) is not int or not 0 <= received <= RELEASE["bytes"]:
                    received = 0
                return {"phase": phase, "message": MESSAGES[phase], "version": RELEASE["version"],
                        "downloaded": received, "total": RELEASE["bytes"],
                        "busy": phase in ACTIVE or bool(self.worker and self.worker.is_alive())}
            except (ValueError, KeyError, TypeError, OSError):
                raise SetupError("Saved Docker setup needs inspection before another attempt.") from None

    def save(self, phase, downloaded=0):
        with self.mutex:
            self._save(phase, downloaded)

    def _save(self, phase, downloaded):
        root = self.home()
        root.mkdir(parents=True, exist_ok=True)
        target = ordinary(root / "job.json")
        temporary = root / ("job-" + secrets.token_hex(12) + ".tmp")
        with temporary.open("x", encoding="utf-8") as output:
            json.dump({"schema": 1, "phase": phase, "version": RELEASE["version"], "downloaded": downloaded}, output)
            output.flush()
            os.fsync(output.fileno())
        # Another readiness process or a virus scanner can briefly deny replacement
        # of a read-open Windows file. Keep the old complete record until it clears.
        for attempt in range(20):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.025)

    def eligible(self, report):
        checks = {row["id"]: row["state"] for row in report.get("checks", [])}
        if (report.get("mode") != "install" or any(checks.get(key) != "pass" for key in ("windows", "architecture", "memory"))
                or report.get("primary_action", {}).get("label") != "Get Docker Desktop" or self.exists()):
            raise SetupError("Installation is available only when Docker is missing on a compatible computer. Check readiness again.")

    def review(self, report):
        with self.mutex:
            self.eligible(report)
            status = self.status()
            if status["busy"]:
                raise SetupError("Docker setup is already running.")
            token = secrets.token_urlsafe(24)
            self.reviewed = (token, time.monotonic() + 5 * 60, status["phase"] == "interrupted")
            return {"review_id": token, "version": RELEASE["version"], "download_bytes": RELEASE["bytes"],
                    "publisher": "Docker Inc", "sha256": RELEASE["sha256"], "previous_installer_check": self.reviewed[2],
                    "changes": ["Download and verify the pinned Docker Desktop installer.",
                                "Open Docker's installer for this Windows account. Follow any Windows permission prompts.",
                                "Complete Docker's terms and first start in Docker Desktop. Reopen this checker after a requested restart."],
                    "terms": "https://www.docker.com/legal/docker-subscription-service-agreement/"}

    def start(self, review_id, report, previous_closed=False):
        with self.mutex:
            review = self.reviewed
            if not review or not secrets.compare_digest(str(review_id), review[0]) or time.monotonic() > review[1]:
                raise SetupError("Review Docker installation again before starting.")
            self.eligible(report)
            if review[2] and previous_closed is not True:
                raise SetupError("Complete or close the earlier Docker installer and confirm that before retrying.")
            if self.status()["busy"]:
                raise SetupError("Docker setup is already running.")
            lock = operation_lock(self.home())
            lock.__enter__()
            try:
                self.reviewed = None
                self.cancelled.clear()
                self.save("downloading")
                self.worker = threading.Thread(target=self.execute, args=(lock,), daemon=True)
                self.worker.start()
            except Exception:
                lock.__exit__(None, None, None)
                raise
            return {"started": True}

    def cancel(self):
        with self.mutex:
            if self.status()["phase"] not in ("downloading", "verifying") or not (self.worker and self.worker.is_alive()):
                raise SetupError("Cancellation is available only before the Docker installer opens.")
            self.cancelled.set()
            return {"cancelling": True}

    def execute(self, lock):
        payload = None
        try:
            root = self.home()
            # Each attempt gets its own ordinary file. Interrupted partials are never executed.
            payload = root / ("docker-" + secrets.token_hex(16) + ".exe")
            if not self.downloader(payload, lambda count: self.save("downloading", count), self.cancelled):
                self.save("cancelled")
                return
            self.save("verifying", RELEASE["bytes"])
            with self.locker(payload):
                with ordinary(payload).open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if checksum != RELEASE["sha256"]:
                    raise SetupError("Installer checksum mismatch")
                self.signer(payload)
                with self.mutex:
                    if self.cancelled.is_set():
                        self.save("cancelled")
                        return
                    if self.exists():
                        self.save("already-installed")
                        return
                    self.save("installing", RELEASE["bytes"])
                code = self.launcher(payload)
                self.save("complete" if code == 0 else "restart-needed" if code == 3010 else "failed")
        except Exception:
            try:
                phase = self.status()["phase"]
                self.save("verification-failed" if phase == "verifying" else "failed")
            except (OSError, SetupError):
                pass
        finally:
            if payload is not None:
                try:
                    ordinary(payload).unlink(missing_ok=True)
                except OSError:
                    pass
            lock.__exit__(None, None, None)
