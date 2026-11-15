# Build on Windows: python -m PyInstaller platform/windows/Stackarr.spec
from pathlib import Path
import hashlib
import json
import os
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parents[1]
caddy_data = []
if os.environ.get("STACKARR_CADDY_BUNDLE"):
    caddy_root = Path(os.environ["STACKARR_CADDY_BUNDLE"]).resolve()
    caddy_lock = json.loads((root / "stackarr/caddy.lock.json").read_text())
    if hashlib.sha256((caddy_root / "caddy.exe").read_bytes()).hexdigest() != caddy_lock["binary_sha256"]:
        raise ValueError("The bundled Caddy does not match the reviewed release.")
    caddy_data = [(str(caddy_root / name), "lan_caddy") for name in ("caddy.exe", "LICENSE")]
a = Analysis(
    [str(root / "platform/windows/launcher_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "stackarr/static"), "stackarr/static"),
           (str(root / "platform/windows/first_run"), "first_run_assets"),
           (str(root / "stackarr/images.lock.json"), "stackarr"),
           (str(root / "stackarr/updates.lock.json"), "stackarr"),
           (str(root / "stackarr/bundled-images.lock.json"), "stackarr"),
           (str(root / "LICENSE"), "."),
           (str(root / "docs/LICENSE-NOTES.md"), "docs"),
           (str(root / "stackarr/caddy.lock.json"), "stackarr"), *caddy_data],
    hiddenimports=collect_submodules("uvicorn"),
    hookspath=[], runtime_hooks=[], excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="StackarrPreview",
          debug=False, strip=False, upx=False, console=False)
