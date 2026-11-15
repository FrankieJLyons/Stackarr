"""Host-consented media roots; browser requests never supply a filesystem path."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .folder_browser import FolderBrowser


def approved(store, roots):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS controller_media_roots (id INTEGER PRIMARY KEY, data TEXT)")
        saved = [json.loads(row[0]) for row in db.execute("SELECT data FROM controller_media_roots ORDER BY id")]
        for root in roots:
            if not any(os.path.normcase(row["path"]) == os.path.normcase(root["path"]) for row in saved):
                FolderBrowser([root])
                saved.append(root)
                db.execute("INSERT INTO controller_media_roots VALUES(?,?)", (len(saved) - 1, json.dumps(root)))
    return saved


def grant(store, path):
    root = {"path": str(Path(path)), "host_path": str(Path(path)), "label": Path(path).name or "Media folder"}
    browser = FolderBrowser([root])
    browser.resolve(0)
    roots = approved(store, [root])
    index = next(index for index, row in enumerate(roots) if os.path.normcase(row["path"]) == os.path.normcase(root["path"]))
    return roots, index


def choose():
    if os.name != "nt":
        raise ValueError("Choose a folder already shared with the installation computer.")
    try:
        with tempfile.TemporaryDirectory(prefix="stackarr-folder-") as temporary:
            report = Path(temporary) / "selection.json"
            arguments = ([sys.executable, "--choose-media-folder", str(report)] if getattr(sys, "frozen", False)
                         else [sys.executable, "-m", "stackarr.media_folders", str(report)])
            result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode or not report.is_file() or report.is_symlink() or report.stat().st_size > 8192:
                raise ValueError("The folder chooser could not finish. Your previous folder is unchanged.")
            selected = json.loads(report.read_text(encoding="utf-8"))
            if not isinstance(selected, dict) or set(selected) != {"path"} or not isinstance(selected["path"], str):
                raise ValueError("The folder chooser could not finish. Your previous folder is unchanged.")
            return selected["path"]
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("The folder chooser did not finish. Close it and choose a folder again.") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("The folder chooser could not finish. Your previous folder is unchanged.") from None


def dialog(report):
    """Run the local picker on its own GUI main thread, with a private result file."""
    import tkinter as tk

    from .media_folder_window import select

    try:
        path = select()
        with Path(report).open("x", encoding="utf-8") as output:
            json.dump({"path": path or ""}, output, ensure_ascii=False)
        return 0
    except (OSError, tk.TclError):
        return 1


if __name__ == "__main__":
    raise SystemExit(dialog(sys.argv[1]) if len(sys.argv) == 2 else 1)
