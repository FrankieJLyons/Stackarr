import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from stackarr.self_update import FILES
from tools.build_windows_installer import OWNER_FILE, OWNER_TEXT, build, signature, stage


def test_installer_cli_accepts_relative_paths_without_resolving_links(tmp_path, monkeypatch):
    from tools import build_windows_installer as installer

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["installer", "--package", "dist/package", "--output", "dist/installers",
                                     "--version", "0.1.1", "--compiler", "tools/ISCC.exe"])
    captured = []
    monkeypatch.setattr(installer, "build", lambda *args, **kw: captured.append(args))
    installer.main()
    assert captured == [(tmp_path / "dist/package", tmp_path / "dist/installers", "0.1.1", tmp_path / "tools/ISCC.exe")]
    # absolute() retains link path components for the existing direct() checks.
    assert installer.absolute_path("link/../output") == tmp_path / "link/../output"


@pytest.fixture
def payload(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in FILES:
        (source / name).write_bytes(("Synthetic " + name).encode())
    manifest = {"schema": 1, "release": "Test", "image": "stackarr:test", "image_id": "sha256:" + "a" * 64,
                "maintenance": {"protocol": 1, "state_schema": 1}, "signin_startup": 1,
                "files": {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES}}
    (source / "manifest.json").write_text(json.dumps(manifest))
    return source


def test_only_verified_manifest_files_are_installed(payload, tmp_path):
    (payload / "private-extra.txt").write_text("not part of package")
    dest = tmp_path / "staged"
    stage(payload, dest)
    assert set(p.name for p in dest.iterdir()) == FILES | {"manifest.json", OWNER_FILE}
    assert (dest / OWNER_FILE).read_text() == OWNER_TEXT
    assert not (dest / "private-extra.txt").exists()


def test_corrupt_package_is_rejected_before_staging(payload, tmp_path):
    (payload / "StackarrPreview.exe").write_bytes(b"changed")
    with pytest.raises(ValueError):
        stage(payload, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows builder")
def test_signed_release_cannot_fall_back_to_unsigned(payload, tmp_path):
    with pytest.raises(ValueError, match="Signing identity"):
        build(payload, tmp_path / "output", "0.1.1", Path("missing.exe"), require_signed=True)
    assert not (tmp_path / "output").exists()


def test_hosted_installer_acceptance_refuses_a_user_machine(monkeypatch):
    from tools.windows_installer_check import run

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable"):
        run()


@pytest.mark.skipif(os.name != "nt", reason="Windows Authenticode command")
@pytest.mark.parametrize("valid,signer,timestamp", [(False, "a" * 40, True), (True, "b" * 40, True), (True, "a" * 40, False)])
def test_unsigned_wrong_publisher_or_missing_timestamp_are_rejected(monkeypatch, tmp_path, valid, signer, timestamp):
    from types import SimpleNamespace

    def inspect(command, **options):
        assert not options.get("shell")
        assert options["env"]["STACKARR_SIGNATURE_FILE"] == str(tmp_path / "fixture.exe")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"valid": valid, "thumbprint": signer, "timestamped": timestamp}))
    monkeypatch.setattr("tools.build_windows_installer.subprocess.run", inspect)
    with pytest.raises(ValueError, match="timestamped signature"):
        signature(tmp_path / "fixture.exe", "a" * 40)
