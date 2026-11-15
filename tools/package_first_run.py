"""Build a separate readiness executable from an explicit source snapshot."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SOURCES = (
    "LICENSE", "docs/FIRST-RUN-READINESS.md", "stackarr/__init__.py",
    "stackarr/first_run.py", "stackarr/first_run_server.py", "stackarr/first_run_smoke.py", "stackarr/first_run_docker.py",
    "stackarr/docker_runtime.py", "stackarr/docker_networks.py",
    "platform/windows/first_run_entry.py", "platform/windows/StackarrReadiness.spec",
    "platform/windows/first_run/index.html", "platform/windows/first_run/readiness.css",
    "platform/windows/first_run/readiness.js", "tools/package_first_run.py",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(root, output, python):
    root, output, python = root.resolve(), output.resolve(), python.resolve()
    work = root / "build/first-run-readiness" / output.name
    if not output.is_relative_to(root / "dist") or output == root / "dist" or output.exists() or work.exists():
        raise ValueError("Choose a new release directory inside dist with an unused name")
    if os.name != "nt":
        raise ValueError("Build the Windows executable on Windows")
    version = subprocess.check_output([str(python), "-c", "import PyInstaller; print(PyInstaller.__version__)"],
                                      text=True, timeout=10).strip()
    if version != "6.22.3":
        raise ValueError("Use the pinned PyInstaller 6.22.3 build environment")
    source = work / "source"
    source.mkdir(parents=True)
    hashes = {}
    for name in SOURCES:
        original = root / name
        if original.is_symlink() or not original.resolve().is_relative_to(root) or not original.is_file():
            raise ValueError("Readiness source must be an ordinary workspace file")
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        hashes[name] = digest(target)
    output.mkdir(parents=True)
    temp = work / "temp"
    temp.mkdir()
    environment = {**os.environ, "TEMP": str(temp), "TMP": str(temp)}
    # Snapshot root is the only application import path passed to PyInstaller.
    environment.pop("PYTHONPATH", None)
    subprocess.run([str(python), "-m", "PyInstaller", "--distpath", str(output),
                    "--workpath", str(work / "objects"), str(source / "platform/windows/StackarrReadiness.spec")],
                   cwd=source, env=environment, check=True, timeout=180,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    shutil.copyfile(source / "LICENSE", output / "LICENSE")
    (output / "README.txt").write_text(
        "Stackarr first-run readiness - unsigned private preview\n\n"
        "Open StackarrReadiness.exe. Python and Docker are not required to open the check page.\n"
        "When Docker is missing, choose Install Docker Desktop, review the changes, then Download & install.\n"
        "The official pinned download needs internet access (about 637 MB); checksum and publisher are checked before launch.\n"
        "Follow Docker's installer prompts. Open Docker Desktop from Start, finish its setup, then choose Check again.\n"
        "Windows feature permission and requested restarts remain your choice through official setup.\n"
        "Close checks stops only this checker after setup has finished or its download is cancelled.\n"
        "This package checks prerequisites; it does not install the dashboard or media apps.\n"
        "Use your separate Stackarr preview package after the checks pass.\n"
        "Clean-PC, installation and reboot acceptance remain separate.\n", encoding="utf-8")
    manifest = {"schema": 1, "signed": False, "release": output.name, "build_tool": "PyInstaller " + version,
                "python": subprocess.check_output([str(python), "-c", "import platform; print(platform.python_version())"],
                                                   text=True, timeout=10).strip(),
                "scope": "Independent prerequisite checks and reviewed Docker installation; no dashboard, Seerr image or personal state.",
                "source_files": hashes, "files": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output.iterdir()):
            bundle.write(path, output.name + "/" + path.name)
    checksum = digest(archive)
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    return {"archive": str(archive), "sha256": checksum, "source_files": len(hashes)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[1], args.output, args.build_python), indent=2))
