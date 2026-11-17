"""Opt-in current-user sign-in startup for an already configured Docker installation.

No Docker settings, services, firewall rules or other startup entries are changed.
Registration points to a verified package, while SelfUpdates resumes the active
managed release. Startup never installs a new stack or opens a browser/dialog.
"""

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from .backup_policy import direct
from .deployment import DeploymentError
from .first_run_docker import operation_lock
from .self_update import SelfUpdates, package, pending, read, write

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
OWNER = "stackarr-signin-v1"
WAIT_SECONDS = 180


class StartupError(ValueError):
    pass


class Registry:
    """Only named values under HKCU Run; never delete the shared key."""

    def get(self, name):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, kind = winreg.QueryValueEx(key, name)
                return value if kind == winreg.REG_SZ else (value, kind)
        except FileNotFoundError:
            return None

    def set(self, name, value):
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def installation(root, *, require_runtime=True):
    root = direct(Path(root))
    if not root.is_dir():
        raise StartupError("Complete Stackarr setup before enabling startup.")
    if read(root / "installation.json").get("owner") != "stackarr-docker-preview-v1":
        raise StartupError("This folder is not a supported Stackarr installation.")
    if not require_runtime and not (root / "stackarr-runtime.json").exists():
        return root
    runtime = read(root / "stackarr-runtime.json")
    release = runtime.get("release", "")
    if len(release) != 64 or any(c not in "0123456789abcdef" for c in release):
        raise StartupError("Stackarr's active release needs inspection.")
    return root


class Registration:
    def __init__(self, root, executable, registry=None):
        self.root = direct(Path(root))
        self.executable = direct(Path(executable))
        identity = hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:20]
        self.name = "Stackarr-" + identity
        self.command = subprocess.list2cmdline([str(self.executable), "--startup-resume", str(self.root)])
        if len(self.command) > 260:
            raise StartupError("Use a shorter Stackarr package/data path for Windows sign-in startup.")
        self.registry = registry or Registry()
        self.receipt = self.root / "signin-startup.json"

    def saved(self):
        if not self.receipt.exists():
            return None
        value = read(self.receipt)
        if (value.get("owner") != OWNER or value.get("name") != self.name
                or not isinstance(value.get("command"), str) or type(value.get("enabled")) is not bool):
            raise StartupError("The startup receipt needs inspection; no registration was changed.")
        return value

    def status(self):
        saved = self.saved()
        current = self.registry.get(self.name)
        return {"enabled": bool(saved and saved["enabled"] and current == saved["command"]),
                "conflict": current is not None and (not saved or current != saved["command"])}

    def enable(self):
        installation(self.root, require_runtime=False)
        if (self.root / "stackarr-removed.json").exists() or pending(self.root):
            raise StartupError("Finish reviewed reinstall or maintenance recovery before enabling startup.")
        if self.executable.name != "StackarrPreview.exe":
            raise StartupError("Use the complete packaged Windows application for startup.")
        manifest = package(self.executable.parent)
        if manifest.get("signin_startup") != 1:
            raise StartupError("This package does not support sign-in startup.")
        with operation_lock(self.root / "signin-registration"):
            saved = self.saved()
            current = self.registry.get(self.name)
            if current is not None and (not saved or current != saved["command"]):
                raise StartupError("Another startup value uses this name. It was left unchanged.")
            if not (self.root / "stackarr-runtime.json").exists():
                receipt = read(self.root / "installation.json")
                ports = [receipt.get(key) for key in ("port", "controller_port")]
                if any(type(value) is not int or not 1 <= value <= 65535 for value in ports):
                    raise StartupError("Open Stackarr and complete setup before enabling startup.")
                # Capture the already-running, ownership-checked release without
                # starting/installing anything or relying on inherited default ports.
                SelfUpdates(self.root, package_root=self.executable.parent).adopt(
                    port=ports[0], controller_port=ports[1])
            installation(self.root)
            # Persist intent first: a crash must not leave an unidentifiable Run value.
            value = {"owner": OWNER, "name": self.name, "command": self.command,
                     "enabled": True, "executable_sha256": manifest["files"]["StackarrPreview.exe"]}
            write(self.receipt, value)
            try:
                self.registry.set(self.name, self.command)
            except Exception:
                # Retain the new intent if the registry write took effect before raising.
                if self.registry.get(self.name) != self.command:
                    if saved:
                        write(self.receipt, saved)
                    else:
                        value["enabled"] = False
                        write(self.receipt, value)
                raise
        return self.status()

    def disable(self):
        if not self.root.is_dir() or not self.receipt.exists():
            if self.registry.get(self.name) is not None:
                raise StartupError("The startup entry has no matching receipt. It was left unchanged.")
            return {"enabled": False, "conflict": False}
        with operation_lock(self.root / "signin-registration"):
            saved = self.saved()
            current = self.registry.get(self.name)
            if current is not None and (not saved or current != saved["command"]):
                raise StartupError("The startup entry was changed outside Stackarr. It was left unchanged.")
            if current is not None:
                self.registry.delete(self.name)
            if saved:
                saved["enabled"] = False
                write(self.receipt, saved)
        return self.status()

    def authorized(self):
        saved = self.saved()
        return bool(saved and saved["enabled"] and saved["command"] == self.command
                    and self.registry.get(self.name) == self.command)


def docker_ready():
    from .docker_runtime import inspect

    result = inspect(enabled=True)
    # Existing projects do not need capacity for a new Docker network.
    checks = [row for row in result["checks"] if row["check"] != "network capacity"]
    return bool(checks and any(row["check"] == "engine" for row in checks)
                and all(row["ok"] for row in checks))


def resume(root, executable, *, registry=None, ready=docker_ready, start=None,
           clock=time.monotonic, sleep=time.sleep, wait_seconds=WAIT_SECONDS):
    """Wait only for readiness; never replay a failed mutating start in a loop."""
    validated = False
    try:
        root = installation(root)
        validated = True
        registration = Registration(root, executable, registry)
        if not registration.authorized():
            return 0
        manifest = package(registration.executable.parent)
        saved = registration.saved()
        if (manifest.get("signin_startup") != 1
                or manifest["files"]["StackarrPreview.exe"] != saved["executable_sha256"]):
            raise StartupError("The startup executable changed. Review startup settings again.")
        identity = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:20]
        # The ordinary packaged handoff uses this same lock. A simultaneous
        # manual open and sign-in launch must not create competing controllers.
        with operation_lock(root.parent / (".stackarr-start-" + identity)):
            deadline = clock() + wait_seconds
            while True:
                if not registration.authorized() or (root / "stackarr-removed.json").exists():
                    return 0
                if pending(root):
                    raise StartupError("Maintenance recovery needs review. Open Stackarr manually.")
                if ready():
                    break
                if clock() >= deadline:
                    raise StartupError("Docker did not become ready. Open Docker Desktop, then open Stackarr.")
                sleep(min(5, max(0, deadline - clock())))
            # Recheck opt-out/removal after the potentially slow readiness probe.
            if not registration.authorized() or (root / "stackarr-removed.json").exists():
                return 0
            if pending(root):
                raise StartupError("Maintenance recovery needs review. Open Stackarr manually.")
            (start or (lambda: SelfUpdates(root).start()))()
            write(root / "signin-status.json", {"state": "started", "checked_at": time.time(),
                  "message": "Stackarr resumed after Windows sign-in."})
        return 0
    except Exception as exc:
        # Never leak exception details, credentials or launch arguments to reports.
        message = str(exc) if isinstance(exc, StartupError) else "Stackarr could not resume. Open Stackarr to check Docker, storage and recovery."
        try:
            if validated and Path(root).is_dir():
                write(direct(Path(root)) / "signin-status.json",
                      {"state": "needs-attention", "checked_at": time.time(), "message": message})
        except (OSError, ValueError):
            pass
        return 1


def settings(root):
    """A local, explicit enable/disable review; never enabled by installation."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Tk()
    window.title("Stackarr startup")
    window.geometry("560x420")
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Start after Windows sign-in", font=("Segoe UI", 18)).pack(anchor="w")
    ttk.Label(frame, wraplength=500, text=(
        "Start your saved Stackarr installation quietly when you sign in to this Windows account. "
        "Stackarr waits up to about three minutes for Docker, then reports a problem if it is unavailable.\n\n"
        "Enable Docker Desktop's own start-at-sign-in setting separately. This does not run before sign-in, "
        "open a browser, start the optional HTTPS gateway, or change your other apps' startup settings.\n\n"
        "Complete setup first and keep this application folder. You can turn this off here at any time."
    )).pack(anchor="w", pady=14)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status, wraplength=500).pack(anchor="w", pady=8)
    registration = Registration(root, Path(sys.executable))

    def refresh():
        try:
            value = registration.status()
            status.set("An external change needs inspection." if value["conflict"] else
                       "Enabled for this Windows account." if value["enabled"] else "Not enabled.")
            report = registration.root / "signin-status.json"
            if report.exists():
                last = read(report)
                if last.get("state") == "needs-attention":
                    status.set(status.get() + " Last startup needs attention; open Stackarr manually.")
        except Exception:
            status.set("Startup settings could not be read. Check the installation folder.")

    def change(enabled):
        try:
            (registration.enable if enabled else registration.disable)()
        except (OSError, ValueError, DeploymentError):
            messagebox.showerror("Startup unchanged", "Complete setup and any maintenance recovery first. Use the complete package and check folder access. Changed or unrecognized startup entries are preserved.", parent=window)
        refresh()

    ttk.Button(frame, text="Enable at sign-in", command=lambda: change(True)).pack(anchor="w", pady=4)
    ttk.Button(frame, text="Turn off automatic startup", command=lambda: change(False)).pack(anchor="w", pady=4)
    refresh()
    window.mainloop()


def command(mode, root):
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return 1
    if mode == "resume":
        return resume(root, Path(sys.executable))
    if mode == "disable":
        try:
            return 1 if Registration(root, Path(sys.executable)).disable()["conflict"] else 0
        except Exception:
            return 1
    settings(root)
    return 0
