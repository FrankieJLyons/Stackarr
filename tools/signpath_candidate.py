"""Prepare and verify same-run SignPath artifacts; never publish or access private keys."""

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

from stackarr import __version__
from stackarr.backup_policy import direct
from stackarr.self_update import FILES, package
from tools.build_windows_installer import absolute_path, signature, stage


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def pe_content(data):
    """Compare PE content while allowing only Authenticode/checksum/alignment changes.

    This is deliberately stricter than the Authenticode image hash: no sections,
    resources or overlay bytes may change. Only an EOF certificate table is accepted.
    """
    data = bytearray(data)
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Expected a Windows PE binary.")
    pe = struct.unpack_from("<I", data, 60)[0]
    optional = pe + 24
    if optional + 152 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header.")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10b, 0x20b):
        raise ValueError("Unsupported PE format.")
    security = optional + (112 if magic == 0x20b else 96) + 32
    offset, size = struct.unpack_from("<II", data, security)
    if offset or size:
        if offset < security + 8 or offset % 8 or size < 8 or offset + size != len(data):
            raise ValueError("Unexpected certificate-table layout.")
        data = data[:offset]
    data[optional + 64:optional + 68] = b"\0" * 4
    data[security:security + 8] = b"\0" * 8
    data.extend(b"\0" * (-len(data) % 8))
    return bytes(data)


def accept(original, signed, thumbprint):
    original, signed = direct(original), direct(signed)
    if not re.fullmatch(r"[a-fA-F0-9]{40}", thumbprint):
        raise ValueError("Configure the approved certificate thumbprint before signing.")
    if pe_content(original.read_bytes()) != pe_content(signed.read_bytes()):
        raise ValueError("Signing changed executable content; refusing the returned artifact.")
    signature(signed, thumbprint)


def metadata(path, *, inno=False):
    response = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$v=[System.Diagnostics.FileVersionInfo]::GetVersionInfo($env:STACKARR_SIGNATURE_FILE); "
         "@{product=$v.ProductName;version=$v.ProductVersion} | ConvertTo-Json -Compress"],
        env=os.environ | {"STACKARR_SIGNATURE_FILE": str(path)}, capture_output=True, text=True,
        timeout=30, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(response.stdout)
    # Inno 6 uses fixed, space-padded resource fields (60/50 characters).
    # Match those exact bytes in SignPath too; do not permit arbitrary suffixes.
    expected = {"product": "Stackarr".ljust(60) if inno else "Stackarr",
                "version": __version__.ljust(50) if inno else __version__}
    if value != expected:
        raise ValueError("The PE product/version does not match this Stackarr source revision: " + repr(value))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare(source, work, kind, revision):
    source, work = direct(source), direct(work)
    if kind not in ("launcher", "package") or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Choose a supported artifact and exact source revision.")
    if kind == "package":
        provenance = package(source)
        if provenance.get("source_dirty") is not False or provenance.get("alpha_test"):
            raise ValueError("A clean source checkout is required for signing.")
    else:
        provenance = json.loads((source / "build-metadata.json").read_text(encoding="utf-8-sig"))
    if provenance.get("source_revision") != revision:
        raise ValueError("The artifact and signing workflow source revisions differ.")
    if kind == "launcher" and provenance.get("artifacts_sha256", {}).get("StackarrPreview.exe") != digest(source / "StackarrPreview.exe"):
        raise ValueError("The launcher does not match its build receipt.")
    metadata(source / "StackarrPreview.exe")
    work.mkdir(parents=True)  # No reuse of partially signed state from an earlier request.
    if kind == "package":
        stage(source, work / "payload")
    request = work / "request-launcher"
    request.mkdir()
    shutil.copyfile(source / "StackarrPreview.exe", request / "StackarrPreview.exe")
    save(work / "state.json", {"kind": kind, "source_revision": revision, "version": __version__})


def compile_command(work, compiler):
    return [str(direct(compiler)), f"/DPayloadDir={work / 'payload'}", f"/DAppVersion={__version__}",
            f"/DOutputDir={work / 'compiled'}", f"/DOutputName=Stackarr-{__version__}-Windows-x64-Setup",
            f"/DExternalSigningDir={work / 'uninstaller-cache'}",
            str(Path(__file__).resolve().parents[1] / "platform/windows/Stackarr.iss")]


def export_uninstaller(work, compiler):
    cache = work / "uninstaller-cache"
    cache.mkdir()
    (work / "compiled").mkdir()
    result = subprocess.run(compile_command(work, compiler), capture_output=True, text=True, timeout=900)
    files = list(cache.iterdir())
    # Inno's documented first pass intentionally stops after writing an unsigned e32.
    # A normal compile failure or an accidentally completed unsigned build is not success.
    if (result.returncode == 0 or len(files) != 1 or not files[0].name.startswith("uninst-")
            or files[0].suffix != ".e32" or list((work / "compiled").glob("*.exe"))):
        raise ValueError("Inno did not export exactly one uninstaller for external signing.\n" + result.stdout + result.stderr)
    metadata(files[0], inno=True)
    request = work / "request-uninstaller"
    request.mkdir()
    shutil.copyfile(files[0], request / "StackarrUninstaller.exe")
    return files[0].name


def finish(work, binary, state):
    output = work / "verified"
    output.mkdir()
    dest = output / binary.name
    shutil.copyfile(binary, dest)
    checksums = {dest.name: digest(dest)}
    if state["kind"] == "package":
        payload = work / "payload"
        package(payload)
        name = f"Stackarr-{__version__}-Windows-x64"
        archive = output / (name + ".zip")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for filename in sorted(FILES | {"manifest.json"}):
                bundle.write(payload / filename, name + "/" + filename)
        checksums[archive.name] = digest(archive)
    for name, value in checksums.items():
        (output / (name + ".sha256")).write_text(f"{value}  {name}\n", encoding="ascii")
    save(output / "signing-receipt.json", state | {"signed": True, "files": checksums,
        "scope": "Verified signing candidate only; no release publication or physical acceptance implied."})


def receive(work, returned, component, thumbprint, compiler=None):
    work, returned = direct(work), direct(returned)
    state = json.loads((work / "state.json").read_text())
    if state["version"] != __version__:
        raise ValueError("Signing state belongs to another version.")
    names = {"launcher": "StackarrPreview.exe", "uninstaller": "StackarrUninstaller.exe", "installer": "StackarrSetup.exe"}
    name = names[component]
    if {p.name for p in returned.iterdir()} != {name}:
        raise ValueError("SignPath must return exactly the requested binary.")
    original = work / ("request-" + component) / name
    signed = returned / name
    accept(original, signed, thumbprint)
    if state.get("signer_thumbprint", thumbprint.upper()) != thumbprint.upper():
        raise ValueError("Publisher changed during the signing sequence.")
    state["signer_thumbprint"] = thumbprint.upper()
    state[component + "_sha256"] = digest(signed)
    if component == "launcher":
        if state["kind"] == "launcher":
            finish(work, signed, state)
        else:
            shutil.copyfile(signed, work / "payload/StackarrPreview.exe")
            path = work / "payload/manifest.json"
            manifest = json.loads(path.read_text())
            manifest["files"]["StackarrPreview.exe"] = digest(signed)
            manifest["signed"] = True
            readme = work / "payload/README.txt"
            guide = readme.read_text(encoding="utf-8")
            guide = guide.replace("The launcher is unsigned.", "The launcher is signed.")
            guide = guide.replace("This unsigned public beta", "This signed public beta candidate")
            readme.write_text("SIGNING CANDIDATE: launcher signature verified; public release acceptance remains pending.\n\n" + guide,
                              encoding="utf-8")
            manifest["files"]["README.txt"] = digest(readme)
            save(path, manifest)
            package(work / "payload")
            state["uninstaller_cache_name"] = export_uninstaller(work, compiler)
    elif component == "uninstaller":
        if state["kind"] != "package" or not state.get("launcher_sha256"):
            raise ValueError("Sign the package launcher first.")
        cache = work / "uninstaller-cache" / state["uninstaller_cache_name"]
        shutil.copyfile(signed, cache)
        subprocess.run(compile_command(work, compiler), check=True, timeout=900)
        artifact = work / "compiled" / f"Stackarr-{__version__}-Windows-x64-Setup.exe"
        metadata(artifact, inno=True)
        request = work / "request-installer"
        request.mkdir()
        shutil.copyfile(artifact, request / "StackarrSetup.exe")
    else:
        if state["kind"] != "package" or not state.get("uninstaller_sha256"):
            raise ValueError("Sign and embed the uninstaller first.")
        artifact = work / "compiled" / f"Stackarr-{__version__}-Windows-x64-Setup.exe"
        shutil.copyfile(signed, artifact)
        finish(work, artifact, state)
    save(work / "state.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("prepare")
    first.add_argument("--input", type=absolute_path, required=True)
    first.add_argument("--kind", choices=("launcher", "package"), required=True)
    first.add_argument("--revision", required=True)
    first.add_argument("--work", type=absolute_path, required=True)
    later = sub.add_parser("receive")
    later.add_argument("--work", type=absolute_path, required=True)
    later.add_argument("--returned", type=absolute_path, required=True)
    later.add_argument("--component", choices=("launcher", "uninstaller", "installer"), required=True)
    later.add_argument("--thumbprint", required=True)
    later.add_argument("--compiler", type=absolute_path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.input, args.work, args.kind, args.revision)
    else:
        receive(args.work, args.returned, args.component, args.thumbprint, args.compiler)


if __name__ == "__main__":
    main()
