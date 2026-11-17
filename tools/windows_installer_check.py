"""Hosted disposable-Windows installer acceptance; never run on a household host."""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from stackarr.self_update import FILES
from stackarr.windows_startup import Registration, Registry
from tools.build_windows_installer import build


def run():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("This installer acceptance runs only on a disposable GitHub-hosted Windows runner.")
    target = Path(os.environ["LOCALAPPDATA"]) / "Programs/Stackarr"
    data = Path(os.environ["LOCALAPPDATA"]) / "Stackarr/DockerPreview"
    if target.exists() or data.exists():
        raise RuntimeError("The runner already has Stackarr state; refusing to install over it.")
    compiler = Path(os.environ["ProgramFiles(x86)"]) / "Inno Setup 6/ISCC.exe"
    launcher = Path("dist/StackarrPreview.exe").resolve()
    results = {}
    with tempfile.TemporaryDirectory(prefix="stackarr-installer-acceptance-") as temporary:
        scratch = Path(temporary)
        payload = scratch / "payload"
        payload.mkdir()
        for name in FILES:
            (payload / name).write_bytes(launcher.read_bytes() if name == "StackarrPreview.exe" else
                                       ("Synthetic installer fixture: " + name).encode())
        manifest = {"schema": 1, "release": "Stackarr-Installer-Test", "maintenance": {"protocol": 1, "state_schema": 1},
                    "image": "stackarr:installer-fixture", "image_id": "sha256:" + "a" * 64,
                    "signin_startup": 1,
                    "files": {name: hashlib.sha256((payload / name).read_bytes()).hexdigest() for name in FILES}}
        (payload / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        artifact = build(payload, scratch / "output", "0.0.0", compiler)
        results["compiler"] = True

        def execute(executable, *arguments):
            return subprocess.run([str(executable), *arguments], timeout=180,
                                  creationflags=subprocess.CREATE_NO_WINDOW).returncode

        # A real unrelated directory at the fixed destination must block installation.
        target.mkdir(parents=True)
        sentinel = target / "unrelated.txt"
        sentinel.write_bytes(b"preserved application-folder file")
        assert execute(artifact, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") != 0
        assert sentinel.read_bytes() == b"preserved application-folder file"
        assert not (target / "StackarrPreview.exe").exists()
        sentinel.unlink()
        target.rmdir()
        results["foreign_destination_refused"] = True

        assert execute(artifact, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") == 0
        assert (target / "StackarrPreview.exe").read_bytes() == launcher.read_bytes()
        assert not data.exists()  # No implicit first-run setup or startup registration.
        shortcuts = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Stackarr"
        assert all((shortcuts / name).is_file() for name in ("Stackarr.lnk", "Startup settings.lnk", "Recover Stackarr.lnk"))
        results["install_and_shortcuts"] = True

        # Exercise real HKCU registration on the hosted runner with no Docker access.
        data.mkdir(parents=True)
        (data / "installation.json").write_text(json.dumps({"owner": "stackarr-docker-preview-v1"}), encoding="utf-8")
        (data / "stackarr-runtime.json").write_text(json.dumps({"release": "b" * 64}), encoding="utf-8")
        reg = Registration(data, target / "StackarrPreview.exe")
        other = Registry()
        other_name = "StackarrInstallerAcceptance-Unrelated"
        if other.get(other_name) is not None:
            raise RuntimeError("The fixture registry name already exists.")
        other.set(other_name, "synthetic unrelated startup entry")
        try:
            assert not reg.status()["enabled"]
            assert reg.enable()["enabled"]
            results["real_current_user_registration"] = True
            sentinel.write_bytes(b"preserved application-folder file")
            private = data / "retained-settings.txt"
            private.write_bytes(b"preserved test settings")
            # Repeat install exercises the receipt-owned upgrade path.
            assert execute(artifact, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") == 0
            assert sentinel.read_bytes() == b"preserved application-folder file"
            assert private.read_bytes() == b"preserved test settings"
            results["repeat_install_preserves_untracked_files"] = True
            assert execute(target / "uninstall/unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") == 0
            assert not (target / "StackarrPreview.exe").exists()
            assert sentinel.read_bytes() == b"preserved application-folder file"
            assert private.read_bytes() == b"preserved test settings"
            assert not reg.status()["enabled"] and reg.registry.get(reg.name) is None
            assert other.get(other_name) == "synthetic unrelated startup entry"
            results["uninstall_preserves_state_and_foreign_startup"] = True
        finally:
            # Only the exact synthetic value created above is eligible for removal.
            if other.get(other_name) == "synthetic unrelated startup entry":
                other.delete(other_name)
    Path("test-results").mkdir(exist_ok=True)
    Path("test-results/windows-installer.json").write_text(json.dumps({"passed": True, "checks": results,
        "limits": "Synthetic package on hosted Windows; real clean-Windows/Docker/reboot/signing acceptance remains open."}, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "checks": results}))


if __name__ == "__main__":
    run()
