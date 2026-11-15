"""Host-local, one-use reinstall approval when the dashboard has been removed."""

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .backup_policy import direct
from .deployment import DeploymentError
from .self_update import ID, TERMINAL, SelfUpdates, read
from .store import Conflict


def review(root, action="reinstall"):
    if action not in {"reinstall", "repair"}:
        raise DeploymentError("Choose reviewed Stackarr repair or reinstall.")
    updates = SelfUpdates(Path(root))
    value = updates.review(action)
    identity = uuid.uuid4().hex
    directory = direct(updates.home / (action + "-reviews"))
    directory.mkdir(exist_ok=True, mode=0o700)
    with direct(directory / (identity + ".enc")).open("xb") as output:
        output.write(updates.cipher().store.cipher.encrypt(json.dumps({"expires": time.time() + 300, "review": value}).encode()))
    return {"format": 1, "action": action, "state": str(updates.root), "id": identity, "notice": value["notice"],
            "release": updates.release(value["source"]["release"])[1]["release"]}


def approve(value, action="reinstall"):
    if action not in {"repair", "reinstall"} or value.get("action", "reinstall") != action or value.get("format") != 1 or not ID.fullmatch(value.get("id") or ""):
        raise DeploymentError("Review this installation's " + action + " first.")
    updates = SelfUpdates(Path(value["state"]))
    path = direct(updates.home / (action + "-reviews") / (value["id"] + ".enc"))
    try:
        saved = json.loads(updates.cipher().store.cipher.decrypt(path.read_bytes()))
    except Exception:
        raise Conflict("The " + action + " review expired, changed or was already used. Review it again.") from None
    if saved["expires"] <= time.time():
        raise Conflict("The " + action + " review expired. Review it again.")
    if saved["review"]["action"] != action:
        raise Conflict("Review the requested Stackarr action again.")
    # Atomic rename claims the one-use review across independent local processes.
    claimed = direct(path.with_suffix(".claimed"))
    try:
        path.rename(claimed)
    except OSError:
        raise Conflict("The " + action + " review was already used. Review it again.") from None
    try:
        return updates.approve(saved["review"])
    finally:
        claimed.unlink(missing_ok=True)


def command(mode, request_file, report_file, action="reinstall"):
    try:
        request = read(Path(request_file))
        result = review(request["state"], action) if mode == "review" else approve(request, action)
        status = 0
    except Exception as exc:
        result = {"passed": False, "message": str(exc) if isinstance(exc, (DeploymentError, Conflict)) else
                  "Stackarr " + action + " could not finish. Restore Docker and writable storage, check saved ports, then retry. Existing apps, settings and media are retained."}
        status = 1
    with Path(report_file).open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    return status


def wizard(state, action="reinstall"):
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox

    root = tk.Tk()
    repairing = action == "repair"
    root.title("Repair Stackarr" if repairing else "Reinstall Stackarr")
    root.geometry("640x330")
    root.resizable(False, False)
    text = tk.StringVar(value=("Review repair to bring back Stackarr's dashboard and private controller using its saved release, password, settings and backups. Restore Docker and folder access first. Your media apps keep running.\n\nRetained state: " if repairing else "Stackarr was removed with its settings kept.\n\nReview reinstall to bring back the dashboard and private controller with your existing password, settings and backups. Your media apps keep running.\n\nRetained state: ") + str(state))
    tk.Label(root, textvariable=text, wraplength=580, justify="left", padx=25, pady=25).pack()
    executor = ThreadPoolExecutor(max_workers=1)

    def failed(exc):
        messagebox.showerror("Stackarr " + action + " needs attention", str(exc) if isinstance(exc, (DeploymentError, Conflict)) else
                             "Restore Docker and writable storage, then review again. Your media apps and data are retained.", parent=root)
        button.config(state="normal")

    def wait(future, complete):
        if not future.done():
            root.after(150, lambda: wait(future, complete))
            return
        try:
            complete(future.result())
        except Exception as exc:
            failed(exc)

    def poll(identity):
        try:
            updates = SelfUpdates(Path(state))
            job = read(updates.home / "jobs" / identity / "job.json")
            text.set(job["message"])
            if job["phase"] not in TERMINAL | {"needs-recovery"}:
                root.after(1000, lambda: poll(identity))
            elif job["phase"] == "succeeded":
                webbrowser.open(f"http://localhost:{job['target']['port']}")
                button.config(text="Close", state="normal", command=root.destroy)
            else:
                button.config(state="normal")
        except Exception as exc:
            failed(exc)

    def inspected(value):
        if not messagebox.askyesno("Review Stackarr " + action, value["notice"] + "\n\nSaved release: " + value["release"], parent=root):
            text.set("Repair cancelled. Existing settings are retained." if repairing else "Reinstall cancelled. Stackarr remains removed; your settings are retained.")
            button.config(state="normal")
            return
        text.set("Checking copies of your retained settings… Keep this window open.")
        wait(executor.submit(approve, value, action), lambda result: poll(result["id"]))

    def inspect():
        button.config(state="disabled")
        text.set("Checking Docker, saved ports, settings and the encrypted checkpoint before making changes…")
        wait(executor.submit(review, state, action), inspected)

    button = tk.Button(root, text="Review " + action, command=inspect, padx=15, pady=8)
    button.pack()
    tk.Button(root, text="Close" if repairing else "Leave Stackarr removed", command=root.destroy).pack(pady=8)
    root.mainloop()
    executor.shutdown(wait=False)
