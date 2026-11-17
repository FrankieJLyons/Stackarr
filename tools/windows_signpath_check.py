"""Rehearse cloud-signing handoffs with an ephemeral test certificate on hosted Windows.

No SignPath API calls, production identity, Docker calls, or release publication.
The certificate is created and removed only on a disposable GitHub-hosted runner.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from stackarr import __version__
from stackarr.self_update import FILES, package
from tools.build_windows_installer import signature
from tools.signpath_candidate import digest, prepare, receive, save


def powershell(script, **env):
    script = ("Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') "
              "-ErrorAction Stop; " + script)
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            env=os.environ | env, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Hosted signing rehearsal PowerShell failed: " + result.stderr)
    return result.stdout.strip()


def run():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("Signing rehearsal requires a disposable GitHub-hosted Windows runner.")
    target = Path(os.environ["LOCALAPPDATA"]) / "Programs/Stackarr"
    runtime = Path(os.environ["LOCALAPPDATA"]) / "Stackarr"
    if target.exists() or runtime.exists():
        raise RuntimeError("Refusing to rehearse over existing Stackarr files.")
    thumbprint = powershell(
        "$ErrorActionPreference='Stop'; "
        "$c=New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=Stackarr disposable signing test' "
        r"-CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddDays(1); "
        "$store=New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','LocalMachine'); "
        "$store.Open('ReadWrite'); $store.Add($c); $store.Close(); $c.Thumbprint")
    results = {}
    try:
        sign_tool = powershell(
            "Get-ChildItem \"${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/signtool.exe\" | "
            "Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName")
        if not Path(sign_tool).is_file():
            raise RuntimeError("Windows SDK SignTool is required for the rehearsal.")
        with tempfile.TemporaryDirectory(prefix="stackarr-signpath-rehearsal-") as temporary:
            scratch = Path(temporary)
            source = scratch / "source"
            source.mkdir()
            for name in FILES:
                if name == "StackarrPreview.exe":
                    shutil.copyfile("dist/StackarrPreview.exe", source / name)
                else:
                    (source / name).write_bytes(b"Synthetic signing fixture, never a distributable release.")
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            save(source / "manifest.json", {"schema": 1, "release": "Stackarr-Signing-Test",
                "maintenance": {"protocol": 1, "state_schema": 1}, "signin_startup": 1,
                "image": "stackarr:signing-fixture", "image_id": "sha256:" + "a" * 64,
                "source_revision": revision, "source_dirty": False,
                "files": {name: digest(source / name) for name in FILES}})
            work = scratch / "work"
            prepare(source, work, "package", revision)
            compiler = Path(os.environ["ProgramFiles(x86)"]) / "Inno Setup 6/ISCC.exe"
            names = {"launcher": "StackarrPreview.exe", "uninstaller": "StackarrUninstaller.exe", "installer": "StackarrSetup.exe"}
            for component, name in names.items():
                returned = scratch / ("returned-" + component)
                returned.mkdir()
                signed = returned / name
                shutil.copyfile(work / ("request-" + component) / name, signed)
                subprocess.run([sign_tool, "sign", "/sha1", thumbprint, "/fd", "SHA256", "/tr",
                                "http://timestamp.digicert.com", "/td", "SHA256", str(signed)], check=True, timeout=90)
                print(powershell(
                    "$s=Get-AuthenticodeSignature -LiteralPath $env:TEST_SIGNED_FILE; "
                    "@{status=[string]$s.Status;timestamped=($null -ne $s.TimeStamperCertificate);"
                    "publisherMatches=($s.SignerCertificate.Thumbprint -eq $env:TEST_CERTIFICATE)} | ConvertTo-Json -Compress",
                    TEST_SIGNED_FILE=str(signed), TEST_CERTIFICATE=thumbprint), flush=True)
                receive(work, returned, component, thumbprint, compiler)
                results[component + "_verified"] = True
            package(work / "payload")
            receipt = json.loads((work / "verified/signing-receipt.json").read_text())
            assert receipt["signed"] and receipt["source_revision"] == revision
            assert all(digest(work / "verified" / name) == expected for name, expected in receipt["files"].items())
            results["final_checksums_and_manifest"] = True
            installer = work / "verified" / f"Stackarr-{__version__}-Windows-x64-Setup.exe"
            subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"], check=True, timeout=180)
            uninstaller = target / "uninstall/unins000.exe"
            signature(uninstaller, thumbprint)
            signature(target / "StackarrPreview.exe", thumbprint)
            results["installed_launcher_and_uninstaller_signed"] = True
            subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=180)
            deadline = time.monotonic() + 10
            while target.exists() and time.monotonic() < deadline:
                time.sleep(.1)  # Inno's self-delete helper can outlive the uninstaller process.
            assert not target.exists() and not runtime.exists()
            results["no_runtime_created"] = True
    finally:
        powershell(
            r"$ErrorActionPreference='Stop'; foreach ($location in @('CurrentUser\My','LocalMachine\Root')) { "
            r"$path='Cert:\' + $location + '\' + $env:TEST_CERTIFICATE; "
            "if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }",
            TEST_CERTIFICATE=thumbprint)
    Path("test-results").mkdir(exist_ok=True)
    save(Path("test-results/signpath-rehearsal.json"), {"passed": True, "checks": results,
        "limits": "Ephemeral local test trust only. No SignPath approval/API/public certificate tested. No real Docker payload."})
    print(json.dumps(results))


if __name__ == "__main__":
    run()
