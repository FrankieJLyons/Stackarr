"""Local setup window. Bundling supplies Python; recipients need no terminal."""

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .pairing import PairingGate


def instance_lock(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (root / "launcher.lock").open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Stackarr is already open for this account.") from None
    return handle


def data_directory():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            raise RuntimeError("Windows local application data folder is unavailable.")
        return Path(base) / "Stackarr" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Stackarr"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "stackarr"


def main(root=None, ready_report=None, open_browser=True):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    import uvicorn

    from .folder_picker import FolderPicker
    from .server import create_app

    window = tk.Tk()
    window.title("Stackarr setup preview")
    window.geometry("560x560")
    window.minsize(520, 500)
    gate = PairingGate()
    picker = FolderPicker()
    listener = socket.socket()
    lock = None
    try:
        root = Path(root) if root is not None else data_directory()
        if not root.is_absolute():
            raise ValueError("Choose an absolute Stackarr data directory")
        lock = instance_lock(root)
        # Retain the bound socket throughout startup; no port-selection race.
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        app = create_app(root, origin=origin, host_checks=True, pairing=gate, host_install=True, folder_picker=picker)
        server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, proxy_headers=False))
    except Exception:
        listener.close()
        if lock:
            lock.close()
        messagebox.showerror("Stackarr could not start", "Check whether Stackarr is already open, then check access to your application-data folder and local network permissions. No applications were installed.")
        window.destroy()
        return
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Welcome to Stackarr", font=("Segoe UI", 20)).pack(anchor="w")
    ttk.Label(frame, text="Plan your media server in your browser.\nKeep this window open while using this local preview.", wraplength=450).pack(anchor="w", pady=12)
    status = tk.StringVar(value="Starting local setup…")
    ttk.Label(frame, textvariable=status, wraplength=450).pack(anchor="w", pady=10)
    open_button = ttk.Button(frame, text="Open Stackarr", command=lambda: webbrowser.open(origin), state="disabled")
    open_button.pack(anchor="w", pady=5)
    runtime_status = tk.StringVar(value="Check Docker before installing new apps. Existing apps can be connected without it.")
    ttk.Label(frame, textvariable=runtime_status, wraplength=450).pack(anchor="w", pady=5)
    runtime_result = []

    def check_runtime():
        from .docker_runtime import inspect

        runtime_button.configure(state="disabled")
        runtime_status.set("Checking Docker on this computer…")
        threading.Thread(target=lambda: runtime_result.append(inspect(enabled=True)), daemon=True).start()

    runtime_button = ttk.Button(frame, text="Check Docker", command=check_runtime)
    runtime_button.pack(anchor="w", pady=5)
    displayed = [None]
    approve = ttk.Button(frame, text="Approve matching browser code", state="disabled",
                         command=lambda: gate.approve(displayed[0]))
    approve.pack(anchor="w", pady=5)
    ttk.Label(frame, text="Install selected Docker apps only after reviewing the plan. Keep this window open during installation. Your progress is saved.", wraplength=450).pack(anchor="w", pady=12)
    opened = [False]

    def update():
        if runtime_result:
            result = runtime_result.pop()
            runtime_status.set("Docker is ready for new apps." if result["state"] == "ready" else
                               " ".join(row["detail"] for row in result["checks"] if not row["ok"]))
            runtime_button.configure(state="normal")
        if not thread.is_alive():
            status.set("Stackarr stopped. Close this window and reopen the launcher to retry.")
            open_button.configure(state="disabled")
            approve.configure(state="disabled")
            return
        if server.started:
            open_button.configure(state="normal")
            if not opened[0]:
                opened[0] = True
                if ready_report:
                    import json

                    with Path(ready_report).open("x", encoding="utf-8") as output:
                        json.dump({"url": origin}, output)
                if open_browser:
                    webbrowser.open(origin)
            displayed[0] = gate.display_code()
            status.set(f"Browser code: {displayed[0]}\nApprove only if this matches your browser." if displayed[0]
                       else "Local dashboard ready. First-time setup asks you to approve a matching code here.")
            approve.configure(state="normal" if displayed[0] else "disabled")
            selection = picker.take()
            if selection:
                try:
                    path = filedialog.askdirectory(parent=window, title="Choose your Stackarr media folder", mustexist=True)
                except tk.TclError:
                    path = ""
                picker.complete(selection, path)
        window.after(500, update)

    def close():
        if app.state.deployments and (any(row["state"] in ("queued", "running") for row in app.state.deployments.rows()) or app.state.deployments.actions.busy()):
            messagebox.showinfo("App operation in progress", "Let this installation or app action finish before closing Stackarr. You can keep using the browser.")
            return
        gate.revoke()
        server.should_exit = True
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    window.after(100, update)
    window.mainloop()
    thread.join(timeout=5)
    listener.close()
    lock.close()


if __name__ == "__main__":
    main()
