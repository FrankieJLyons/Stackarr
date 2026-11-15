"""Local folder selection without Windows shell extensions or network enumeration."""

import os
from pathlib import Path


def local_drives():
    import ctypes

    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    return [f"{chr(65 + index)}:\\" for index in range(26)
            if mask & (1 << index) and kernel.GetDriveTypeW(f"{chr(65 + index)}:\\") in (2, 3)]


def children(path):
    result = []
    with os.scandir(path) as entries:
        for entry in entries:
            try:
                if (not entry.name.startswith(("$", ".")) and entry.is_dir(follow_symlinks=False)
                        and not getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400):
                    result.append(Path(entry.path))
            except OSError:
                continue
            if len(result) > 1000:
                raise ValueError("This folder has too many subfolders. Choose a smaller folder.")
    return sorted(result, key=lambda row: row.name.casefold())


def new_folder(parent, name):
    if (not name or len(name) > 255 or name in {".", ".."} or name != name.strip()
            or name.endswith(".") or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in name)):
        raise ValueError("Use a simple folder name without slashes or special characters.")
    path = Path(parent) / name
    path.mkdir()
    return path


def select():
    import tkinter as tk
    from tkinter import simpledialog, ttk

    from .folder_browser import FolderBrowser

    drives = local_drives()
    if not drives:
        raise OSError("No local media drives are available")
    window = tk.Tk()
    window.title("Choose your Stackarr media folder")
    window.geometry("700x520")
    window.minsize(540, 400)
    window.attributes("-topmost", True)
    selected = ""
    current, folders = None, []
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)
    ttk.Label(frame, text="Where will your media live?", font=("Segoe UI", 16, "bold")).grid(sticky="w")
    ttk.Label(frame, text="Choose one folder for movies, TV and downloads. Existing files stay in place.",
              wraplength=620).grid(row=1, sticky="w", pady=(6, 14))
    navigation = ttk.Frame(frame)
    navigation.grid(row=2, sticky="ew")
    ttk.Label(navigation, text="Drive").pack(side="left", padx=(0, 8))
    drive = ttk.Combobox(navigation, values=drives, state="readonly", width=12)
    drive.pack(side="left")
    location = tk.StringVar()
    ttk.Entry(frame, textvariable=location, state="readonly").grid(row=3, sticky="ew", pady=(10, 8))
    listing = ttk.Frame(frame)
    listing.grid(row=4, sticky="nsew")
    scrollbar = ttk.Scrollbar(listing, orient="vertical")
    scrollbar.pack(side="right", fill="y")
    folders_list = tk.Listbox(listing, font=("Segoe UI", 11), activestyle="dotbox", exportselection=False,
                              yscrollcommand=scrollbar.set)
    folders_list.pack(side="left", fill="both", expand=True)
    scrollbar.configure(command=folders_list.yview)
    status = tk.StringVar(value="Open folders with a double-click, then choose the folder shown above.")
    ttk.Label(frame, textvariable=status, wraplength=620).grid(row=5, sticky="w", pady=10)
    actions = ttk.Frame(frame)
    actions.grid(row=6, sticky="ew")

    def show(path):
        nonlocal current, folders
        try:
            rows = children(path)
        except (OSError, ValueError):
            status.set("This folder could not be opened. Choose another folder.")
            return
        current, folders = Path(path), rows
        location.set(str(current))
        folders_list.delete(0, tk.END)
        for row in folders:
            folders_list.insert(tk.END, row.name)
        up.configure(state="disabled" if current == current.parent else "normal")
        choose.configure(state="disabled" if current == current.parent else "normal")
        status.set("Open a folder with a double-click, or choose the folder shown above.")

    def open_selected(event=None):
        indexes = folders_list.curselection()
        if indexes:
            show(folders[indexes[0]])

    def finish():
        nonlocal selected
        try:
            FolderBrowser([{"path": str(current), "host_path": str(current), "label": "Media"}]).resolve(0)
        except (OSError, ValueError):
            status.set("Choose an available dedicated folder, rather than a drive or a folder link.")
            return
        selected = str(current)
        window.destroy()

    def create_folder():
        name = simpledialog.askstring("New media folder", "Folder name", parent=window)
        if name is None:
            return
        try:
            path = new_folder(current, name)
        except (OSError, ValueError):
            status.set("The folder could not be created. Use a new simple name in a writable folder.")
            return
        show(path)

    up = ttk.Button(navigation, text="Up one folder", command=lambda: show(current.parent))
    up.pack(side="left", padx=10)
    ttk.Button(actions, text="New folder…", command=create_folder).pack(side="left")
    choose = ttk.Button(actions, text="Choose this folder", command=finish)
    choose.pack(side="right")
    ttk.Button(actions, text="Cancel", command=window.destroy).pack(side="right", padx=10)
    folders_list.bind("<Double-Button-1>", open_selected)
    folders_list.bind("<Return>", open_selected)
    drive.bind("<<ComboboxSelected>>", lambda event: show(Path(drive.get())))
    preferred = next((value for value in drives if value[:2].casefold() != os.environ.get("SystemDrive", "C:").casefold()), drives[0])
    drive.set(preferred)
    show(Path(preferred))
    window.lift()
    window.focus_force()
    try:
        window.mainloop()
    finally:
        try:
            window.destroy()
        except tk.TclError:
            pass
    return selected
