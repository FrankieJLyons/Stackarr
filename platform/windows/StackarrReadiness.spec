# Independent build: python -m PyInstaller --distpath dist/first-run-readiness --workpath build/first-run-readiness platform/windows/StackarrReadiness.spec
from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
a = Analysis(
    [str(root / "platform/windows/first_run_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "platform/windows/first_run"), "first_run_assets"),
           (str(root / "LICENSE"), ".")],
    hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="StackarrReadiness",
          debug=False, strip=False, upx=False, console=False)
