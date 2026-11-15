"""Local recovery entry point; no browser upload of backup keys or host paths."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .deployment import DeploymentError
from .host_recovery import Recovery


def command(mode, request_file, report_file):
    """Two-step host-local automation also used by packaged Docker acceptance."""
    try:
        value = json.loads(Path(request_file).read_text(encoding="utf-8-sig"))
        recovery = Recovery(value["bundle"], value["keyfile"], value["package"])
        if mode == "review":
            result = recovery.review(value["destination"], value["media"], value.get("port", 28000), value.get("controller_port", 28010))
        else:
            result = recovery.execute(value)
        status = 0
    except Exception as exc:
        result = {"passed": False, "message": str(exc) if isinstance(exc, DeploymentError) else "Recovery could not finish. Check the chosen files, Docker and the saved recovery directory. Existing apps and media are preserved."}
        status = 1
    with Path(report_file).open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    return status


def wizard():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("Recover Stackarr")
    root.geometry("620x290")
    root.resizable(False, False)
    text = tk.StringVar(value="Recover Stackarr on an empty installation.\n\nYou need your encrypted recovery file, its separately saved recovery key, and access to your preserved media. Existing apps and volumes will not be overwritten. Media is never restored or deleted.")
    tk.Label(root, textvariable=text, wraplength=560, justify="left", padx=25, pady=25).pack()
    executor = ThreadPoolExecutor(max_workers=1)

    def wait(future, done):
        if not future.done():
            root.after(200, wait, future, done)
            return
        try:
            done(future.result())
        except Exception as exc:
            messagebox.showerror("Recovery needs attention", str(exc) if isinstance(exc, DeploymentError) else "Recovery could not complete. Check Docker and the chosen files. Existing apps and media were preserved.", parent=root)
            button.config(state="normal")

    def restored(result):
        state = result["destination"]
        text.set("Recovery completed. Your Stackarr password and saved app logins are preserved. Backup schedules are paused until reviewed. Opening the recovered dashboard…")
        package = Path(sys.executable).parent
        subprocess.Popen(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
                          str(package / "Start-StackarrPreview.ps1"), "-StateDirectory", state],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        button.config(text="Close", state="normal", command=root.destroy)

    def reviewed(review):
        apps = ", ".join(review["apps"])
        if not messagebox.askyesno("Review recovery", "Recover " + apps + "?\n\n" + review["notice"] + "\n\nNew state: " + review["destination"], parent=root):
            button.config(state="normal")
            return
        target = Path(review["destination"])
        # A review alongside the new state also supports a bounded retry after interruption.
        saved = target.parent / ("stackarr-recovery-review-" + review["id"] + ".json")
        with saved.open("x", encoding="utf-8") as file:
            json.dump(review, file)
        text.set("Restoring configuration into new Docker volumes…\n\nImages may need to download. Keep this window open. Media files stay in their existing folders.")
        recovery = Recovery(review["bundle"], review["keyfile"], review["package"])
        wait(executor.submit(recovery.execute, review), restored)

    def choose():
        bundle = filedialog.askopenfilename(title="Choose your encrypted Stackarr recovery file", filetypes=[("Stackarr recovery", "*.stackarr-recovery")], parent=root)
        if not bundle:
            return
        key = filedialog.askopenfilename(title="Choose the separately saved recovery key", filetypes=[("Recovery key", "*.json")], parent=root)
        if not key:
            return
        target = filedialog.askdirectory(title="Choose an empty folder for the recovered Stackarr state", parent=root)
        if not target:
            return
        button.config(state="disabled")
        text.set("Verifying the recovery file and key before making changes…")
        recovery = Recovery(bundle, key, Path(sys.executable).parent)

        def inspected(roots):
            media = {}
            for old in roots:
                path = filedialog.askdirectory(title="Choose preserved media for: " + old, parent=root)
                if not path:
                    button.config(state="normal")
                    return
                media[old] = path
            wait(executor.submit(recovery.review, target, media), reviewed)

        def inspect():
            with recovery.opened() as (_, metadata):
                return recovery.roots(metadata)
        wait(executor.submit(inspect), inspected)

    def guarded_choose():
        try:
            choose()
        except Exception as exc:
            messagebox.showerror("Recovery needs attention", str(exc) if isinstance(exc, DeploymentError) else "The recovery files could not be opened.", parent=root)
            button.config(state="normal")

    def resume():
        filename = filedialog.askopenfilename(title="Choose the saved Stackarr recovery review", filetypes=[("Recovery review", "*.json")], parent=root)
        if not filename:
            return
        try:
            review = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            if not messagebox.askyesno("Resume recovery", "Retry the saved recovery into " + review["destination"] + "?\n\nOnly the same new recovery containers may be used. Their configuration is restored again from the verified backup.", parent=root):
                return
            recovery = Recovery(review["bundle"], review["keyfile"], review["package"])
            button.config(state="disabled")
            text.set("Verifying and resuming the saved recovery… Media stays in its existing folders.")
            wait(executor.submit(recovery.execute, review), restored)
        except Exception as exc:
            messagebox.showerror("Recovery needs attention", str(exc) if isinstance(exc, DeploymentError) else "Choose the review saved by Recover Stackarr.", parent=root)

    button = tk.Button(root, text="Choose recovery files", command=guarded_choose, padx=15, pady=8)
    button.pack()
    tk.Button(root, text="Resume a saved recovery", command=resume).pack(pady=6)
    root.mainloop()
    executor.shutdown(wait=False)
