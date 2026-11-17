"""Deterministic PE version resource for the Windows launcher."""

import re
from pathlib import Path

from stackarr import __version__


def write(path):
    if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        raise ValueError("Windows signing requires a numeric three-part release version.")
    numeric = tuple(map(int, __version__.split("."))) + (0,)
    values = {"CompanyName": "Stackarr contributors", "FileDescription": "Stackarr launcher",
              "FileVersion": __version__, "InternalName": "StackarrPreview", "ProductName": "Stackarr",
              "ProductVersion": __version__, "OriginalFilename": "StackarrPreview.exe"}
    entries = ",\n".join(f"StringStruct({key!r}, {value!r})" for key, value in values.items())
    data = (f"VSVersionInfo(ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, "
            "mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), "
            f"kids=[StringFileInfo([StringTable('040904B0', [{entries}])]), "
            "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return str(path)
