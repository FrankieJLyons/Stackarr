"""Compile a verified complete package into an explicitly signed or unsigned installer."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from stackarr.backup_policy import direct
from stackarr.self_update import FILES, package

OWNER_FILE = "stackarr-installer-owner.txt"
OWNER_TEXT = "Stackarr per-user installer v1\n"


def absolute_path(value):
    # CLI paths may be relative. Do not resolve links before direct() can reject them.
    return Path(value).absolute()


def signature(path, thumbprint):
    """Read public signer identity only; never import/export a certificate or key."""
    system = Path(os.environ["SystemRoot"])
    response = subprocess.run(
        [str(system / "System32/WindowsPowerShell/v1.0/powershell.exe"), "-NoProfile", "-Command",
         "$ErrorActionPreference='Stop'; "
         "Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1'); "
         "$s=Get-AuthenticodeSignature -LiteralPath $env:STACKARR_SIGNATURE_FILE; "
         "@{valid=($s.Status -eq 'Valid');thumbprint=$s.SignerCertificate.Thumbprint;"
         "timestamped=($null -ne $s.TimeStamperCertificate)} | ConvertTo-Json -Compress"],
        env=os.environ | {"STACKARR_SIGNATURE_FILE": str(path)}, capture_output=True, text=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    result = json.loads(response.stdout) if response.returncode == 0 else {}
    if (result.get("valid") is not True or result.get("timestamped") is not True
            or result.get("thumbprint", "").casefold() != thumbprint.casefold()):
        raise ValueError("A valid timestamped signature from the selected publisher is required.")


def stage(source, destination):
    """Copy only manifest payloads and reverify; never admit a recursive directory."""
    source, destination = direct(source), direct(destination)
    manifest = package(source)
    if manifest.get("signin_startup") != 1:
        raise ValueError("Choose a package with the reviewed sign-in startup controls.")
    destination.mkdir()
    for name in sorted(FILES | {"manifest.json"}):
        shutil.copyfile(direct(source / name), destination / name)
    package(destination)
    (destination / OWNER_FILE).write_text(OWNER_TEXT, encoding="ascii")
    return manifest


def build(source, output, version, compiler, *, certificate=None, sign_tool=None, require_signed=False):
    if os.name != "nt":
        raise ValueError("The Windows installer compiler must run on Windows.")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Choose an explicit semantic release version.")
    if require_signed and not certificate:
        raise ValueError("Signing identity is required; refusing an unsigned release build.")
    if bool(certificate) != bool(sign_tool):
        raise ValueError("Supply both a certificate thumbprint and SignTool path.")
    if certificate and not re.fullmatch(r"[A-Fa-f0-9]{40}", certificate):
        raise ValueError("Choose a SHA-1 certificate thumbprint from the publisher's Windows certificate store.")
    compiler, output = direct(compiler), direct(output)
    if not compiler.is_file():
        raise ValueError("Inno Setup ISCC.exe is unavailable.")
    name = f"Stackarr-{version}-Windows-x64-Setup" + ("" if certificate else "-unsigned")
    artifact = output / (name + ".exe")
    if artifact.exists():
        raise ValueError("Choose a new output location; existing installers are not overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stackarr-installer-") as scratch:
        staged = Path(scratch) / "payload"
        manifest = stage(Path(source), staged)
        command = [str(compiler), f"/DPayloadDir={staged}", f"/DAppVersion={version}",
                   f"/DOutputDir={output}", f"/DOutputName={name}"]
        if certificate:
            sign_tool = direct(sign_tool)
            if not sign_tool.is_file() or '"' in str(sign_tool):
                raise ValueError("Choose an installed Windows SDK SignTool executable.")
            signature(staged / "StackarrPreview.exe", certificate)
            signing = f'$q{sign_tool}$q sign /sha1 {certificate} /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $f'
            command += ["/DSignedBuild=1", "/Spublisher=" + signing]
        command.append(str(Path(__file__).resolve().parents[1] / "platform/windows/Stackarr.iss"))
        subprocess.run(command, check=True, timeout=900)
    if not artifact.is_file():
        raise ValueError("The compiler did not produce the expected installer.")
    if certificate:
        signature(artifact, certificate)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_suffix(".exe.sha256").write_text(f"{digest}  {artifact.name}\n", encoding="ascii")
    receipt = {"version": version, "source_revision": manifest.get("source_revision"),
               "package_release": manifest["release"], "sha256": digest, "signed": bool(certificate),
               "scope": "current-user launcher installation; runtime state and media retained on uninstall"}
    artifact.with_suffix(".exe.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=absolute_path, required=True)
    parser.add_argument("--output", type=absolute_path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--compiler", type=absolute_path, required=True)
    parser.add_argument("--certificate-sha1")
    parser.add_argument("--sign-tool", type=absolute_path)
    parser.add_argument("--require-signed", action="store_true")
    args = parser.parse_args()
    print(build(args.package, args.output, args.version, args.compiler, certificate=args.certificate_sha1,
                sign_tool=args.sign_tool, require_signed=args.require_signed))


if __name__ == "__main__":
    main()
